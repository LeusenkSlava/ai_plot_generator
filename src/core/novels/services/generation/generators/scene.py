import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, Novel, Roadmap, Scene
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.generators.scene_roadmap_validator import (
    SceneRoadmapValidator,
)
from src.core.novels.services.generation.prompts.cast import (
    find_protagonist,
    render_cast,
)
from src.core.novels.services.generation.prompts.context import render_place_time
from src.core.novels.services.generation.prompts.text import (
    RUSSIAN_OUTPUT_NOTE,
    parse_day,
)
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)


class SceneGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        scene_service: SceneService,
        character_service: CharacterService,
        generator: GeneratorProtocol,
        validator: SceneRoadmapValidator,
        max_validation_retries: int = 3,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service
        self._character_service = character_service
        self._validator = validator
        self._max_validation_retries = max_validation_retries

    async def generate(
        self,
        roadmap_id: int,
        previous_scenes: list[Scene] | None = None,
        story_context: str | None = None,
        order: int | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> Scene:
        """Следующая сцена шага роадмапа. previous_scenes — уже сыгранные сцены новеллы для связности,
        story_context — изложение истории после предыдущей сцены (рендер фактов и персонажей для промпта сцены
        и валидатора). order — сквозной номер сцены в новелле.

        Чтение состояния и запись сцены — отдельные короткие транзакции; LLM-вызовы
        и валидация идут между ними и не держат соединение Postgres.
        """
        # 1) Read-фаза: короткая транзакция.
        async with step():
            roadmap = await self._roadmap_service.get(roadmap_id)
            if not roadmap:
                raise GenerationError(f"Roadmap with id {roadmap_id} not found")

            novel = await self._novel_service.get(roadmap.novel_id)
            if not novel:
                raise GenerationError(f"Novel with id {roadmap.novel_id} not found")

            characters = await self._character_service.list_by_novel(novel.id) or []

            # Позиция сцены внутри шага роадмапа (для финала шага и подсказки в промпте).
            # Считаем только валидные сцены (needs_review=False): сцена, не прошедшая
            # валидацию из Задачи 1, не продвигает шаг и не должна сбивать номер.
            scenes_in_step = await self._scene_service.list_by_roadmap(roadmap.id) or []
            step_position = sum(1 for s in scenes_in_step if not s.needs_review) + 1
            # Сквозной номер сцены по всей новелле: по нему идёт идемпотентность и
            # упорядочивание в NovelState, поэтому он не должен сбрасываться на каждом шаге.
            if order is None:
                order = len(await self._scene_service.list_by_novel(novel.id) or []) + 1
            is_final_for_roadmap = step_position >= max(roadmap.scenes_count, 1)
            roadmaps = await self._roadmap_service.list_by_novel(novel.id) or []
            is_last_roadmap = roadmap.step_id >= max(
                (r.step_id for r in roadmaps), default=0
            )
            is_final_for_novel = is_final_for_roadmap and is_last_roadmap

        # 2) LLM-фаза: сборка промпта и ретрай-цикл — без транзакции.
        prompt = self.__create_prompt(
            novel,
            roadmap,
            characters,
            step_position,
            previous_scenes or [],
            story_context,
        )

        characters_by_name = {c.name: c for c in characters}
        protagonist = find_protagonist(characters)
        # Сцена сравнивается на повтор с последней уже сыгранной сценой.
        previous_scene = previous_scenes[-1] if previous_scenes else None

        # Генерация → смысловая проверка соответствия шагу → проверка на повтор →
        # ретрай/ручное вмешательство. Проверки идут ДО записи сцены в БД, чтобы
        # расхождение не съедало шаг молча.
        remaining_retries = self._max_validation_retries
        last_reason: str | None = None
        scene: Scene | None = None
        duplicate_of: Scene | None = None
        matched = False
        while True:
            scene = None
            duplicate_of = None
            try:
                data = await self._generate(prompt, think=False)
                scene_cast = self.__resolve_cast(
                    data.get("characters") or [], characters_by_name, protagonist
                )
                scene = self.__build_scene(
                    data,
                    roadmap,
                    scene_cast,
                    order,
                    is_final_for_roadmap,
                    is_final_for_novel,
                )
                verdict = await self._validator.validate(
                    roadmap=roadmap,
                    scene=scene,
                    story_context=story_context,
                )
            except GenerationError as e:
                # Не удалось собрать участников (неизвестное имя) или сверка упала
                # (транзиентный сбой LLM/неверный ответ). Это сбой текущей попытки —
                # регенерируем сцену, а не валим весь джоб на Kafka-ретрай.
                last_reason = str(e)
            else:
                if verdict.matches:
                    if previous_scene is not None and self.__is_duplicate(
                        scene, previous_scene
                    ):
                        duplicate_of = previous_scene
                        last_reason = (
                            f"сцена повторяет предыдущую «{previous_scene.title}»"
                        )
                    else:
                        matched = True
                        break
                else:
                    last_reason = verdict.reason

            if remaining_retries <= 0:
                break
            remaining_retries -= 1
            prompt = [*prompt, self.__retry_message(roadmap, last_reason, duplicate_of)]

        # Все ретраи исчерпаны. Если ни одна попытка не дала даже сцены (постоянно
        # падал cast) — это ошибка генерации: сохранять под needs_review нечего.
        if scene is None:
            raise GenerationError(
                f"SceneGenerator: не удалось собрать сцену после ретраев: "
                f"{last_reason or 'неизвестная ошибка'}"
            )

        if not matched:
            # Не пропускаем молча: сохраняем сцену с пометкой о ручном вмешательстве и
            # логируем причину. Такая сцена не закрывает шаг и не проигрывается.
            scene.needs_review = True
            scene.review_reason = last_reason or "Сцена не соответствует шагу роадмапа"
            scene.is_final_for_roadmap = False
            scene.is_final_for_novel = False
            self.__log_manual_intervention(roadmap, scene, last_reason)

        # 3) Write-фаза: короткая транзакция только на запись.
        async with step():
            return await self._scene_service.add(scene)

    @staticmethod
    def __resolve_cast(
        names: list[str],
        characters_by_name: dict[str, Character],
        protagonist: Character | None,
    ) -> list[Character]:
        """Превращает имена из ответа LLM в персонажей сцены.

        Протагонист добавляется всегда: сцена подаётся от его лица, поэтому он
        присутствует независимо от того, вернул ли его LLM. Неизвестное имя —
        GenerationError: ретрай-цикл generate() перехватывает её и перегенерирует
        сцену, а не обрывает весь джоб.
        """
        cast: list[Character] = []
        seen: set[int] = set()
        for name in names:
            character = characters_by_name.get(name)
            if character is None:
                raise GenerationError(
                    f"SceneGenerator referenced unknown character '{name}'"
                )
            if character.id not in seen:
                cast.append(character)
                seen.add(character.id)
        if protagonist is not None and protagonist.id not in seen:
            cast.append(protagonist)
        return cast

    @staticmethod
    def __build_scene(
        data: dict,
        roadmap: Roadmap,
        cast: list[Character],
        order: int,
        is_final_for_roadmap: bool,
        is_final_for_novel: bool,
    ) -> Scene:
        """Собирает сцену; место/время по умолчанию наследуются от шага роадмапа."""
        location_slug, time_of_day, day = SceneGenerator.__place_time(data, roadmap)
        return Scene(
            id=None,
            created_at=None,
            updated_at=None,
            roadmap_id=roadmap.id,
            title=data["title"],
            description=data["description"],
            order=order,
            is_final_for_roadmap=is_final_for_roadmap,
            is_final_for_novel=is_final_for_novel,
            character_ids=[c.id for c in cast],
            location_slug=location_slug,
            time_of_day=time_of_day,
            day=day,
        )

    @staticmethod
    def __place_time(
        data: dict, roadmap: Roadmap
    ) -> tuple[str | None, str | None, int | None]:
        """Место/время сцены: явно заданное LLM, иначе — от шага роадмапа."""
        location = (data.get("location_slug") or "").strip() or roadmap.location_slug
        time_of_day = (data.get("time_of_day") or "").strip() or roadmap.time_of_day
        day = parse_day(data.get("day")) or roadmap.day
        return location, time_of_day, day

    @staticmethod
    def __is_duplicate(scene: Scene, previous: Scene | None) -> bool:
        """Сцена повторяет предыдущую, если совпали название, место, день и участники.

        Такое совпадение — признак переигрывания одного и того же бита внутри шага
        (например, две сцены «Проверка зрения» подряд в медпункте).
        """
        if previous is None:
            return False
        if scene.title != previous.title:
            return False
        if scene.location_slug != previous.location_slug:
            return False
        if scene.day != previous.day:
            return False
        return set(scene.character_ids) == set(previous.character_ids)

    @staticmethod
    def __retry_message(
        roadmap: Roadmap, reason: str | None, duplicate_of: Scene | None
    ) -> dict:
        if duplicate_of is not None:
            return {
                "role": "user",
                "content": (
                    f"The scene repeats the previous scene «{duplicate_of.title}»: the same place, "
                    "the same day, and the same participants. Rewrite it so that it moves the plot "
                    "further — a new situation, a new conflict, or new development, not a "
                    "replaying of what already happened. Keep the place and day as in the roadmap step."
                ),
            }
        reason = reason or "not specified"
        return {
            "role": "user",
            "content": (
                f"The scene does not fit the current roadmap step. Return to the step "
                f"«{roadmap.title}» and rewrite the scene so that "
                "it matches it on three axes:\n"
                f"Step event: {roadmap.event}\n"
                f"Step conflict: {roadmap.conflict}\n"
                f"Step change: {roadmap.change}\n"
                "- theme/event — what should happen in this step;\n"
                "- place — the location where the step takes place;\n"
                "- time — the day/stage in which the step takes place.\n"
                "In characters, list only names from the character list above.\n"
                f"Reason: {reason}"
            ),
        }

    @staticmethod
    def __log_manual_intervention(
        roadmap: Roadmap, scene: Scene, reason: str | None
    ) -> None:
        logger.warning(
            "scene: ручная валидация роадмапа не пройдена "
            "(roadmap_id=%s, title=%r, scene_order=%s, reason=%s)",
            roadmap.id,
            roadmap.title,
            scene.order,
            reason or "не указана",
        )

    def __create_prompt(
        self,
        novel: Novel,
        roadmap: Roadmap,
        characters: list[Character],
        step_position: int,
        previous_scenes: list[Scene],
        story_context: str | None,
    ) -> list[dict]:
        scenes_count = max(roadmap.scenes_count, step_position)
        system_prompt = {
            "role": "system",
            "content": (
                "You are a screenwriter for interactive visual novels. "
                "Based on the description of the story and the current roadmap step, create the next scene of this step. "
                "It should continue the previous scenes without repeating them "
                "and move the plot toward the step's event — carry its conflict and reach its change. "
                "The scene should unfold the step's event and establish the place and situation of the action, "
                "but not retell the dialogues themselves. Put the step's conflict into the description as a "
                "concrete crisis or obstacle (what makes the event hard), not just its outcome. Specify:\n"
                "1. title - a short title for the scene.\n"
                "2. description - a description of the place, time, situation, and conflict of the scene, "
                "from which the characters' dialogues will then be generated: "
                "2-4 sentences, no more than 400 characters, no atmospheric details.\n"
                "3. characters - the names of the characters who are in this scene by place and time "
                "(exactly as in the character list). Include only those who belong here; "
                "do not include a character who does not belong here (for example, someone who never leaves "
                "their own location — in a scene elsewhere). Including the protagonist is optional: "
                "they are always present and are added automatically.\n"
                "4. location_slug - the slug of the scene's location: the same as the roadmap step's (empty string "
                "if the step does not set one).\n"
                "5. time_of_day - the slug of the scene's time of day (empty string if the step does not set one); "
                "it may change within the step if it is the same day.\n"
                "6. day - the story day number (integer from 1): the same as the roadmap step's.\n"
                "If the scene starts later in time or in a different place than the previous one, "
                "note this gap directly in description.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "title": string,
                  "description": string,
                  "characters": [string],
                  "location_slug": string,
                  "time_of_day": string,
                  "day": integer
                }
                """
            ),
        }
        # Сначала неизменное для новеллы, потом меняющееся: так работает кеш префикса у провайдера
        user_content = f"Story title: {novel.title}\n" f"Narrative tone: {novel.tone}"
        if characters:
            user_content += f"\nCharacters:\n{render_cast(characters)}"
            protagonist = find_protagonist(characters)
            if protagonist:
                user_content += (
                    f"\n\nProtagonist: {protagonist.name} — the protagonist. "
                    "The scene should be presented through their perception: their goals, feelings, and choices."
                )
        user_content += (
            f"\n\nStep place and time: "
            f"{render_place_time(roadmap.location_slug, roadmap.time_of_day, roadmap.day)}."
        )
        # Блок шага — в голову (стабилен внутри шага, попадает в кэш), а не после
        # динамического изложения и предыдущих сцен.
        user_content += (
            f"\n\nRoadmap step: {roadmap.title}\n"
            f"Step event: {roadmap.event}\n"
            f"Step conflict: {roadmap.conflict}\n"
            f"Step change: {roadmap.change}\n"
            f"Scene number within the step: {step_position} of {scenes_count}"
        )
        if story_context:
            user_content += (
                "\n\nStory so far (the scene must not contradict it; "
                f"do not change characters' outfits without a plot reason):\n{story_context}"
            )
        if previous_scenes:
            # Что произошло, уже есть в изложении — полностью нужна только последняя сцена для стыка
            *earlier, last = previous_scenes
            story_so_far = "".join(f"- {scene.title}\n" for scene in earlier)
            story_so_far += f"- {last.title}: {last.description}"
            user_content += f"\n\nPrevious scenes:\n{story_so_far}"
            user_content += (
                f"\nEnd of the previous scene: "
                f"{render_place_time(last.location_slug, last.time_of_day, last.day)}."
            )
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

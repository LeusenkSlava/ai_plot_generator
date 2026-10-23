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
from src.core.novels.services.generation.prompts.text import parse_day

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
        story_summary: str | None = None,
        order: int | None = None,
    ) -> Scene:
        """Следующая сцена шага роадмапа. previous_scenes — уже сыгранные сцены новеллы для связности,
        story_context — изложение истории после предыдущей сцены (полный рендер для промпта сцены),
        story_summary — только краткое содержание для валидатора (дёшевле). order — сквозной номер сцены в новелле.
        """
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
                    story_context=story_summary,
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
                        return await self._scene_service.add(scene)
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

        # Не пропускаем молча: сохраняем сцену с пометкой о ручном вмешательстве и
        # логируем причину. Такая сцена не закрывает шаг и не проигрывается.
        scene.needs_review = True
        scene.review_reason = last_reason or "Сцена не соответствует шагу роадмапа"
        scene.is_final_for_roadmap = False
        scene.is_final_for_novel = False
        self.__log_manual_intervention(roadmap, scene, last_reason)
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
    def __place_time(data: dict, roadmap: Roadmap) -> tuple[str | None, str | None, int | None]:
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
                    f"Сцена повторяет предыдущую сцену «{duplicate_of.title}»: то же место, "
                    "тот же день и те же участники. Перепиши её так, чтобы она двигала сюжет "
                    "дальше — новая ситуация, новый конфликт или новое развитие, а не "
                    "переигрывание уже случившегося. Место и день оставь как у шага роадмапа."
                ),
            }
        reason = reason or "не указана"
        return {
            "role": "user",
            "content": (
                f"Сцена не подходит для текущего шага роадмапа. Вернись к шагу "
                f"«{roadmap.title}» (цель: {roadmap.goal}) и перепиши сцену так, "
                "чтобы она совпадала с ним по трём осям:\n"
                "- тема/событие — что должно произойти на этом шаге;\n"
                "- место — локация, где происходит шаг;\n"
                "- время — день/этап, в который происходит шаг.\n"
                "Указывай в characters только имена из списка персонажей выше.\n"
                f"Причина: {reason}"
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
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и текущего шага роадмапа создай очередную сцену этого шага. "
                "Она должна продолжать предыдущие сцены, не повторяя их, "
                "и продвигать сюжет к цели шага. "
                "Сцена должна раскрывать цель шага и задавать место и ситуацию действия, "
                "но не пересказывать сами диалоги. Если сцена — кульминация, задай в описании "
                "конкретный кризис или помеху внутри события, а не только его исход. Укажи:\n"
                "1. title - короткое название сцены.\n"
                "2. description - описание места, времени, ситуации и конфликта сцены, "
                "на основе которого дальше будут сгенерированы диалоги персонажей: "
                "2-4 предложения, не больше 400 символов, без атмосферных подробностей.\n"
                "3. characters - имена персонажей, которые находятся в этой сцене по месту и времени "
                "(точно как в списке персонажей). Включай только тех, кому здесь есть место; "
                "не вписывай персонажа, которому тут не место (например, того, кто не покидает "
                "свою локацию, — в сцену в другом месте). Главного героя включать не обязательно: "
                "он присутствует всегда и добавляется автоматически.\n"
                "4. location_slug - slug локации сцены: тот же, что у шага роадмапа (пустая строка, "
                "если шаг его не задаёт).\n"
                "5. time_of_day - slug времени суток сцены (пустая строка, если шаг его не задаёт); "
                "внутри шага может меняться, если это один и тот же день.\n"
                "6. day - номер дня истории (целое число от 1): тот же, что у шага роадмапа.\n"
                "Если сцена начинается позже по времени или в другом месте, чем предыдущая, "
                "обозначь этот разрыв прямо в description.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
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
        user_content = (
            f"Название истории: {novel.title}\n" f"Тон повествования: {novel.tone}"
        )
        if characters:
            user_content += f"\nПерсонажи:\n{render_cast(characters)}"
            protagonist = find_protagonist(characters)
            if protagonist:
                user_content += (
                    f"\n\nГлавный герой: {protagonist.name} — протагонист. "
                    "Сцена должна подаваться через его восприятие: его цели, чувства и выборы."
                )
        user_content += (
            f"\n\nМесто и время шага: "
            f"{render_place_time(roadmap.location_slug, roadmap.time_of_day, roadmap.day)}."
        )
        # Блок шага — в голову (стабилен внутри шага, попадает в кэш), а не после
        # динамического изложения и предыдущих сцен.
        user_content += (
            f"\n\nШаг роадмапа: {roadmap.title}\n"
            f"Цель шага: {roadmap.goal}\n"
            f"Номер сцены в шаге: {step_position} из {scenes_count}"
        )
        if story_context:
            user_content += (
                "\n\nИзложение истории на данный момент (сцена не должна ему противоречить; "
                f"одежду персонажей не меняй без сюжетной причины):\n{story_context}"
            )
        if previous_scenes:
            # Что произошло, уже есть в изложении — полностью нужна только последняя сцена для стыка
            *earlier, last = previous_scenes
            story_so_far = "".join(f"- {scene.title}\n" for scene in earlier)
            story_so_far += f"- {last.title}: {last.description}"
            user_content += f"\n\nПредыдущие сцены:\n{story_so_far}"
            user_content += (
                f"\nКонец предыдущей сцены: "
                f"{render_place_time(last.location_slug, last.time_of_day, last.day)}."
            )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

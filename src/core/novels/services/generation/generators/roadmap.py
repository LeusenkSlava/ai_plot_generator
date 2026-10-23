import logging

from src.core.codex.models import BackgroundTags
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, Novel, Roadmap
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.cast import (
    find_protagonist,
    render_cast,
)
from src.core.novels.services.generation.prompts.context import (
    render_place_time_catalog,
)
from src.core.novels.services.generation.prompts.text import parse_day

logger = logging.getLogger(__name__)


class RoadmapGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
        think: bool = True,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._codex_service = codex_service
        self._reasoning_effort = reasoning_effort
        self._think = think

    async def generate(self, novel_id: int) -> list[Roadmap]:
        novel = await self._novel_service.get(novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {novel_id} not found")

        characters = await self._character_service.list_by_novel(novel.id) or []
        background_tags = await self.__load_background_tags(novel)

        prompt = self.__create_prompt(novel, characters, background_tags)
        data = await self._generate(
            prompt, think=self._think, reasoning_effort=self._reasoning_effort
        )

        roadmap_data = data.get("roadmap")
        if not roadmap_data:
            raise GenerationError("Generator returned no roadmap")

        roadmap = []
        prev_day: int | None = None
        has_catalogue = background_tags is not None
        for step_id, item in enumerate(roadmap_data, start=1):
            day = parse_day(item.get("day"))
            # День не убывает между шагами: пропущенный или «откатившийся» день
            # наследует предыдущий, чтобы таймлайн оставался монотонным.
            if day is None:
                day = prev_day
            elif prev_day is not None and day < prev_day:
                day = prev_day
            prev_day = day

            step = Roadmap(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                step_id=step_id,
                title=item["title"],
                goal=item["goal"],
                # MVP: новеллы линейные, развилок не генерируем
                target_choice=False,
                choice_stakes=None,
                scenes_count=item["scenes_count"],
                # Без каталога локаций/времени (нет вселенной) эти slug'и не имеют
                # смысла — вынуждаем None, чтобы валидатор не сравнивал произвольные строки.
                location_slug=(
                    self.__slug_or_none(item.get("location_slug"))
                    if has_catalogue
                    else None
                ),
                time_of_day=(
                    self.__slug_or_none(item.get("time_of_day"))
                    if has_catalogue
                    else None
                ),
                day=day,
            )
            step = await self._roadmap_service.add(step)
            roadmap.append(step)

        return roadmap

    async def __load_background_tags(self, novel: Novel) -> BackgroundTags | None:
        """Каталог локаций/времени суток вселенной; без вселенной его нет."""
        if novel.universe_id is None:
            return None
        try:
            return await self._codex_service.get_background_tags(novel.universe_id)
        except Exception as e:
            raise GenerationError(f"Codex background tags request failed: {e}") from e

    @staticmethod
    def __slug_or_none(value) -> str | None:
        slug = (value or "").strip()
        return slug or None

    def __create_prompt(
        self,
        novel: Novel,
        characters: list[Character],
        background_tags: BackgroundTags | None,
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и её тона создай роадмап сюжета — "
                "последовательность шагов, из которых складывается линейная история без развилок и выборов игрока. "
                "Количество шагов определи сам исходя из масштаба истории — обычно от 8 до 12; "
                "чем больше шагов, тем богаче история, но каждый шаг должен двигать сюжет вперёд, "
                "а не повторять предыдущий. "
                "Для каждого шага укажи:\n"
                "1. title - короткое название шага.\n"
                "2. goal - ОДНО завершённое событие/бит, которое происходит на этом шаге; "
                "не растягивай шаг на целую арку — он должен укладываться в 1–2 сцены.\n"
                "3. scenes_count - 1 или 2 для обычного шага; финальному шагу и шагам с развязкой "
                "персонажа можно ставить 2 или 3. Ставь 2/3, только если на каждую сцену есть "
                "отдельный бит, иначе сцена переиграет предыдущую.\n"
                "4. location_slug - slug локации, в которой происходит шаг, ТОЛЬКО из списка локаций "
                "(если списка нет — пустая строка).\n"
                "5. time_of_day - slug времени суток шага, ТОЛЬКО из списка времени суток "
                "(если списка нет — пустая строка).\n"
                "6. day - номер дня истории: целое число от 1, не убывает между шагами; "
                "если шаг происходит в тот же день, что и предыдущий, укажи тот же номер.\n"
                "Структура истории — круг Хармана из 8 битов. Держи этот порядок, "
                "не переставляй и не пропускай биты:\n"
                "1. Обычный мир — главный герой в привычной жизни; дай почувствовать его "
                "неудовлетворённость или желание, чтобы было зачем меняться.\n"
                "2. Потребность — конкретная цель/желание героя, задающая направление всей истории; "
                "она же — сквозная линия из описания истории (тайна, цель, возвращение домой, "
                "внутренний конфликт), которую не бросай до финала.\n"
                "3. Переход — событие выбивает героя из привычной жизни в незнакомую ситуацию (завязка).\n"
                "4. Поиск — герой пробует достичь цели, сталкивается с препятствиями, заводит отношения. "
                "Около середины — поворот, который меняет ставки.\n"
                "5. Находка — герой получает то, чего хотел, но в неожиданной или несовершенной форме.\n"
                "6. Цена — за находку приходится платить: потеря, конфликт, последствие. Это реальное "
                "препятствие/угроза срыва перед кульминацией — не веди к ней по прямой.\n"
                "7. Возвращение — герой возвращается в привычную ситуацию, но уже изменённым; "
                "ключевое событие (признание, решение, выступление) разыгрывается здесь.\n"
                "8. Изменение — финальное состояние героя/мира и вывод истории; развязка, "
                "а не обрыв накануне.\n"
                "Разнеси биты по шагам: 8 битов → 8–12 шагов. Первые и последние биты обычно по одному шагу; "
                "биты 4–6 можно растягивать на 2 шага. У значимых персонажей (союзник, соперник, "
                "love interest) веди мини-арку внутри этих битов и разрешай её к битам 7–8, "
                "а не появлением в одной сцене.\n"
                "Разноси действие по месту и времени: не держи всю историю в одной локации, "
                "если сюжет этого не требует; два соседних шага не должны происходить в одной локации "
                "без сюжетной причины. Каждая сцена внутри шага должна соответствовать месту и дню шага.\n"
                "Строй goal только на персонажах из списка ниже; не упоминай в goal персонажей, "
                "которых нет в списке (даже если они существуют во вселенной) — сцены с такими "
                "персонажами не пройдут проверку и будут перегенерированы.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "roadmap": [
                    {
                      "title": string,
                      "goal": string,
                      "scenes_count": integer,
                      "location_slug": string,
                      "time_of_day": string,
                      "day": integer
                    }
                  ]
                }
                """
            ),
        }
        user_content = (
            f"Название: {novel.title}\n"
            f"Описание: {novel.description}\n"
            f"Тон повествования: {novel.tone}"
        )
        if background_tags:
            user_content += (
                "\n\nКаталог места и времени (выбирай только отсюда):\n"
                + render_place_time_catalog(background_tags)
            )
        if characters:
            user_content += f"\nПерсонажи:\n{render_cast(characters)}"
            protagonist = find_protagonist(characters)
            if protagonist:
                user_content += (
                    f"\n\nГлавный герой: {protagonist.name} — протагонист, от чьего лица идёт история. "
                    f"Его арка: {protagonist.arc}. "
                    "Строй сюжет вокруг главного героя: его целей, решений, внутренних конфликтов и отношений."
                )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

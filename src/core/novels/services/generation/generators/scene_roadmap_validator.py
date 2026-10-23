import logging
from dataclasses import dataclass

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Roadmap, Scene

from .base import BaseGenerator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SceneRoadmapVerdict:
    """Результат сверки сцены с шагом роадмапа по трём осям."""

    theme_match: bool
    location_match: bool
    time_match: bool
    reason: str

    @property
    def matches(self) -> bool:
        """Сцена соответствует шагу, только если совпали все три оси."""
        return self.theme_match and self.location_match and self.time_match


class SceneRoadmapValidator(BaseGenerator):
    """Проверяет, что сцена по смыслу соответствует текущему шагу роадмапа.

    Использует LLM: сверяет сцену с целью шага по теме/событию, месту и времени.
    Проверка смысловая — счёт сцен и порядковые номера в неё не передаются.
    """

    def __init__(self, generator: GeneratorProtocol):
        super().__init__(generator)

    async def validate(
        self,
        roadmap: Roadmap,
        scene: Scene,
        story_context: str | None = None,
    ) -> SceneRoadmapVerdict:
        # Точное несовпадение места или дня — отказ без вызова LLM: это дешёвая и
        # надёжная проверка, которую не должен пропустить смысловой валидатор.
        if (
            roadmap.location_slug
            and scene.location_slug
            and roadmap.location_slug != scene.location_slug
        ):
            return SceneRoadmapVerdict(
                True,
                False,
                True,
                f"локация сцены '{scene.location_slug}' не совпадает с локацией шага "
                f"'{roadmap.location_slug}'",
            )
        if (
            roadmap.day is not None
            and scene.day is not None
            and roadmap.day != scene.day
        ):
            return SceneRoadmapVerdict(
                True,
                True,
                False,
                f"день сцены {scene.day} не совпадает с днём шага {roadmap.day}",
            )

        prompt = self.__create_prompt(roadmap, scene, story_context)
        data = await self._generate(prompt, think=False)
        try:
            theme_match = bool(data["theme_match"])
            location_match = bool(data["location_match"])
            time_match = bool(data["time_match"])
            reason = str(data.get("reason") or "").strip()
        except (KeyError, TypeError, ValueError) as e:
            raise GenerationError(
                f"SceneRoadmapValidator returned malformed verdict: {e}"
            ) from e

        return SceneRoadmapVerdict(
            theme_match=theme_match,
            location_match=location_match,
            time_match=time_match,
            reason=reason,
        )

    @staticmethod
    def __create_prompt(
        roadmap: Roadmap,
        scene: Scene,
        story_context: str | None,
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "Ты редактор интерактивной визуальной новеллы. Проверь, соответствует ли "
                "сгенерированная сцена текущему шагу роадмапа ПО СМЫСЛУ. Оцени строго по трём осям:\n"
                "1. theme_match — тема/событие: сцена продвигает сюжет к цели шага "
                "(к тому, что должно произойти на этом шаге), а не переигрывает уже пройденное "
                "и не выполняет цель другого шага;\n"
                "2. location_match — место: сцена происходит в локации, которую задаёт шаг "
                "(или логично продолжает её), а не в другой локации;\n"
                "3. time_match — время: сцена происходит в том дне/этапе, который задаёт шаг "
                "(или логично следует из изложения истории), а не уходит в другой день/этап.\n"
                "Локация и день шага и сцены заданы явно; если они различаются — по "
                "соответствующей оси ставь false. Если место или время у шага не заданы — "
                "по этой оси ставь true, не выдумывай расхождение. Считай расхождением "
                "только явное несоответствие.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "theme_match": boolean,
                  "location_match": boolean,
                  "time_match": boolean,
                  "reason": string
                }
                """
                "\nreason — короткое объяснение расхождения по осям, где есть расхождение; "
                "пустая строка, если всё совпадает."
            ),
        }
        user_content = (
            f"Шаг роадмапа: {roadmap.title}\n"
            f"Цель шага: {roadmap.goal}\n"
            f"Локация шага: {roadmap.location_slug or 'не задана'}\n"
            f"Время суток шага: {roadmap.time_of_day or 'не задано'}\n"
            f"День шага: {roadmap.day if roadmap.day is not None else 'не задан'}"
        )
        if story_context:
            user_content += (
                f"\n\nИзложение истории на данный момент (день/этап и место действия):\n"
                f"{story_context}"
            )
        user_content += (
            f"\n\nСцена: {scene.title}\n"
            f"Описание сцены: {scene.description}\n"
            f"Локация сцены: {scene.location_slug or 'не задана'}\n"
            f"Время суток сцены: {scene.time_of_day or 'не задано'}\n"
            f"День сцены: {scene.day if scene.day is not None else 'не задан'}"
        )
        return [system_prompt, {"role": "user", "content": user_content}]

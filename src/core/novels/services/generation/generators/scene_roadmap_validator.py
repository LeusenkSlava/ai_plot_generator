import logging
from dataclasses import dataclass

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Roadmap, Scene
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE

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
                "You are the editor of an interactive visual novel. Check whether the "
                "generated scene matches the current roadmap step BY MEANING. Judge strictly on three axes:\n"
                "1. theme_match — theme/event: the scene moves the plot toward the step's event, "
                "carries the step's conflict, and reaches the step's change, rather than replaying what "
                "already passed or fulfilling the event of another step;\n"
                "2. location_match — place: the scene takes place in the location set by the step "
                "(or logically continues it), not in another location;\n"
                "3. time_match — time: the scene takes place in the day/stage set by the step "
                "(or logically follows from the story recap), rather than drifting into another day/stage.\n"
                "The step's and scene's location and day are set explicitly; if they differ — set false "
                "on the corresponding axis. If the step's place or time is not set — "
                "set true on that axis, do not invent a mismatch. Treat only an explicit "
                "mismatch as a discrepancy.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "theme_match": boolean,
                  "location_match": boolean,
                  "time_match": boolean,
                  "reason": string
                }
                """
                "\nreason — a short explanation of the discrepancy on the axes where there is one; "
                "empty string if everything matches."
            ),
        }
        user_content = (
            f"Roadmap step: {roadmap.title}\n"
            f"Step event: {roadmap.event}\n"
            f"Step conflict: {roadmap.conflict}\n"
            f"Step change: {roadmap.change}\n"
            f"Step location: {roadmap.location_slug or 'not set'}\n"
            f"Step time of day: {roadmap.time_of_day or 'not set'}\n"
            f"Step day: {roadmap.day if roadmap.day is not None else 'not set'}"
        )
        if story_context:
            user_content += (
                f"\n\nStory so far (day/stage and place of action):\n"
                f"{story_context}"
            )
        user_content += (
            f"\n\nScene: {scene.title}\n"
            f"Scene description: {scene.description}\n"
            f"Scene location: {scene.location_slug or 'not set'}\n"
            f"Scene time of day: {scene.time_of_day or 'not set'}\n"
            f"Scene day: {scene.day if scene.day is not None else 'not set'}"
        )
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"
        return [system_prompt, {"role": "user", "content": user_content}]

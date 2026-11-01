import logging
from dataclasses import dataclass

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    DEFAULT_PROMPT_VARIANT,
    Prompt,
    PromptKey,
    Roadmap,
    Scene,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.prompts.catalog import (
    PromptCatalog,
    render_messages,
)
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE

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

    def __init__(
        self,
        generator: GeneratorProtocol,
        prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._prompts = prompt_catalog

    async def validate(
        self,
        roadmap: Roadmap,
        scene: Scene,
        story_context: str | None = None,
        variant: str = DEFAULT_PROMPT_VARIANT,
        template: Prompt | None = None,
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

        prompt = await self.__create_prompt(
            template, roadmap, scene, story_context, variant
        )
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

    async def __create_prompt(
        self,
        template: Prompt | None,
        roadmap: Roadmap,
        scene: Scene,
        story_context: str | None,
        variant: str,
    ) -> list[dict]:
        if template is None:
            template = await self._prompts.get(PromptKey.SCENE_VALIDATOR, variant)
        story_context_block = ""
        if story_context:
            story_context_block = (
                "\n\nStory so far (day/stage and place of action):\n" f"{story_context}"
            )
        return render_messages(
            template,
            system_vars={"russian_note": RUSSIAN_OUTPUT_NOTE},
            user_vars={
                "step_title": roadmap.title,
                "step_event": roadmap.event,
                "step_conflict": roadmap.conflict,
                "step_change": roadmap.change,
                "step_location": roadmap.location_slug or "not set",
                "step_time_of_day": roadmap.time_of_day or "not set",
                "step_day": roadmap.day if roadmap.day is not None else "not set",
                "story_context_block": story_context_block,
                "scene_title": scene.title,
                "scene_description": scene.description,
                "scene_location": scene.location_slug or "not set",
                "scene_time_of_day": scene.time_of_day or "not set",
                "scene_day": scene.day if scene.day is not None else "not set",
            },
        )

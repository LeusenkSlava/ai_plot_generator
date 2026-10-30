import logging

from src.core.codex.models import BackgroundTags
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, Novel, Roadmap, RoadmapChoice
from src.core.novels.services.crud import (
    CharacterService,
    NovelService,
    RoadmapChoiceService,
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
from src.core.novels.services.generation.prompts.text import (
    RUSSIAN_OUTPUT_NOTE,
    parse_day,
)
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)


class BranchRoadmapGenerator(BaseGenerator):
    """Ленивая генерация альтернативной ветки роадмапа после выбора форка.

    Ветка линейна (без вложенных выборов) и ведёт к собственной концовке: первый шаг
    ветвится от шага выбора (parent_roadmap_id = шаг выбора), дальше — цепочка шагов
    с новым branch_id и глубиной от глубины выбора + 1. В конце генерации у выбранного
    варианта проставляется next_roadmap_id на первый шаг ветки.
    """

    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        roadmap_choice_service: RoadmapChoiceService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
        think: bool = True,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._roadmap_choice_service = roadmap_choice_service
        self._codex_service = codex_service
        self._reasoning_effort = reasoning_effort
        self._think = think

    async def generate(
        self,
        roadmap_choice_id: int,
        *,
        step: TransactionFactory = noop_step,
    ) -> list[Roadmap]:
        # 1) Read-фаза.
        async with step():
            choice = await self._roadmap_choice_service.get(roadmap_choice_id)
            if not choice:
                raise GenerationError(f"Roadmap choice {roadmap_choice_id} not found")
            if choice.next_roadmap_id is not None:
                raise GenerationError(
                    f"Branch for choice {roadmap_choice_id} already generated"
                )
            fork = await self._roadmap_service.get(choice.roadmap_id)
            if not fork:
                raise GenerationError(f"Roadmap {choice.roadmap_id} not found")
            novel = await self._novel_service.get(fork.novel_id)
            if not novel:
                raise GenerationError(f"Novel {fork.novel_id} not found")
            characters = await self._character_service.list_by_novel(novel.id) or []
            roadmaps = await self._roadmap_service.list_by_novel(novel.id) or []

        branch_id = max((r.branch_id for r in roadmaps), default=0) + 1
        start_depth = fork.depth + 1

        # 2) LLM-фаза.
        background_tags = await self.__load_background_tags(novel)
        prompt = self.__create_prompt(
            novel, characters, choice, fork, background_tags
        )
        data = await self._generate(
            prompt, think=self._think, reasoning_effort=self._reasoning_effort
        )
        branch_data = data.get("roadmap")
        if not branch_data:
            raise GenerationError("Branch generator returned no roadmap")

        branch = []
        prev_day: int | None = fork.day
        has_catalogue = background_tags is not None
        for offset, item in enumerate(branch_data):
            depth = start_depth + offset
            day = parse_day(item.get("day"))
            if day is None or (prev_day is not None and day < prev_day):
                day = prev_day
            prev_day = day
            branch.append(
                Roadmap(
                    id=None,
                    created_at=None,
                    updated_at=None,
                    novel_id=novel.id,
                    depth=depth,
                    title=item["title"],
                    event=(item.get("event") or "").strip(),
                    conflict=(item.get("conflict") or "").strip(),
                    change=(item.get("change") or "").strip(),
                    target_choice=False,
                    choice_stakes=None,
                    scenes_count=item["scenes_count"],
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
                    branch_id=branch_id,
                )
            )

        # 3) Write-фаза: цепочка parent + простановка next_roadmap_id у варианта.
        async with step():
            parent_id = fork.id
            first_step_id: int | None = None
            for index, roadmap_step in enumerate(branch):
                roadmap_step.parent_roadmap_id = parent_id
                roadmap_step = await self._roadmap_service.add(roadmap_step)
                branch[index] = roadmap_step
                if first_step_id is None:
                    first_step_id = roadmap_step.id
                parent_id = roadmap_step.id

            if first_step_id is None:
                raise GenerationError("Branch generator produced no steps")
            await self._roadmap_choice_service.update_next_roadmap(
                choice.id, first_step_id
            )

        return branch

    async def __load_background_tags(self, novel: Novel) -> BackgroundTags | None:
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

    @staticmethod
    def __create_prompt(
        novel: Novel,
        characters: list[Character],
        choice: RoadmapChoice,
        fork: Roadmap,
        background_tags: BackgroundTags | None,
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "You are a screenwriter for interactive visual novels. "
                "Create the roadmap of an ALTERNATIVE branch of the story: the protagonist "
                "made a different choice, and now the story diverges and leads to its own ending. "
                "The branch is linear — no branches and no player choices. "
                "Decide the number of steps yourself — usually 3 to 6; keep it tight, each step "
                "moves the plot toward this branch's own resolution. "
                "For each step, specify:\n"
                "1. title - a short title.\n"
                "2. event - ONE completed event/beat of this step (fits into 1-2 scenes).\n"
                "3. conflict - what makes this event hard for the protagonist.\n"
                "4. change - what changes for the protagonist by the end of the step.\n"
                "5. scenes_count - 1 or 2 (the final step may have 2 or 3).\n"
                "6. location_slug - ONLY from the location list (empty string if no list).\n"
                "7. time_of_day - ONLY from the time-of-day list (empty string if no list).\n"
                "8. day - integer from the branch's start day, non-decreasing.\n"
                "Build event/conflict/change only on the characters from the list below; do not "
                "introduce characters who are not in the list. Do not contradict the story so far. "
                "The branch ends with a real resolution, not a cliffhanger cut.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "roadmap": [
                    {
                      "title": string,
                      "event": string,
                      "conflict": string,
                      "change": string,
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
            f"Story title: {novel.title}\n"
            f"Narrative tone: {novel.tone}\n"
            f"Story description: {novel.description}\n"
            f"\nChoice point step: {fork.title}\n"
            f'Choice stakes: {fork.choice_stakes or "the protagonist\'s decision"}\n'
            f"Chosen branch: {choice.text}\n"
            f"Branch direction: {choice.branch_direction or choice.text}\n"
            f"Start day: {fork.day or 1}"
        )
        if background_tags:
            user_content += (
                "\n\nPlace and time catalog (choose only from here):\n"
                + render_place_time_catalog(background_tags)
            )
        if characters:
            user_content += f"\nCharacters:\n{render_cast(characters)}"
            protagonist = find_protagonist(characters)
            if protagonist:
                user_content += (
                    f"\n\nProtagonist: {protagonist.name}. Build the branch around their "
                    "goals, decisions, and relationships."
                )
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"
        return [system_prompt, {"role": "user", "content": user_content}]

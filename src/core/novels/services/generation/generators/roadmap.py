import logging

from src.core.codex.models import BackgroundTags
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    Novel,
    NovelMode,
    Roadmap,
    RoadmapChoice,
)
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


class RoadmapGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        codex_service: CodexService,
        generator: GeneratorProtocol,
        roadmap_choice_service: RoadmapChoiceService | None = None,
        reasoning_effort: str | None = None,
        think: bool = True,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._codex_service = codex_service
        self._roadmap_choice_service = roadmap_choice_service
        self._reasoning_effort = reasoning_effort
        self._think = think

    async def generate(
        self,
        novel_id: int,
        *,
        step: TransactionFactory = noop_step,
    ) -> list[Roadmap]:
        # 1) Read-фаза: короткая транзакция.
        async with step():
            novel = await self._novel_service.get(novel_id)
            if not novel:
                raise GenerationError(f"Novel with id {novel_id} not found")
            characters = await self._character_service.list_by_novel(novel.id) or []

        # 2) LLM-фаза: Codex (HTTP) и генерация — без транзакции.
        background_tags = await self.__load_background_tags(novel)

        prompt = self.__create_prompt(novel, characters, background_tags)
        data = await self._generate(
            prompt, think=self._think, reasoning_effort=self._reasoning_effort
        )

        roadmap_data = data.get("roadmap")
        if not roadmap_data:
            raise GenerationError("Generator returned no roadmap")

        interactive = novel.mode == NovelMode.INTERACTIVE

        roadmap = []
        raw_choices: dict[int, list[dict]] = {}
        prev_day: int | None = None
        has_catalogue = background_tags is not None
        for depth, item in enumerate(roadmap_data, start=1):
            day = parse_day(item.get("day"))
            # День не убывает между шагами: пропущенный или «откатившийся» день
            # наследует предыдущий, чтобы таймлайн оставался монотонным.
            if day is None or (prev_day is not None and day < prev_day):
                day = prev_day
            prev_day = day

            target_choice = bool(item.get("target_choice")) if interactive else False
            choice_stakes = None
            if target_choice:
                choice_stakes = (item.get("choice_stakes") or "").strip() or None

            roadmap_step = Roadmap(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                depth=depth,
                title=item["title"],
                event=(item.get("event") or "").strip(),
                conflict=(item.get("conflict") or "").strip(),
                change=(item.get("change") or "").strip(),
                target_choice=target_choice,
                choice_stakes=choice_stakes,
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
                branch_id=0,
            )
            roadmap.append(roadmap_step)
            if target_choice:
                raw_choices[depth] = item.get("choices") or []

        # 3) Write-фаза: короткая транзакция только на запись. Родительский шаг —
        #    предыдущий шаг цепочки (id известен только после сохранения).
        async with step():
            step_by_depth: dict[int, Roadmap] = {}
            prev_id: int | None = None
            for index, roadmap_step in enumerate(roadmap):
                roadmap_step.parent_roadmap_id = prev_id
                roadmap_step = await self._roadmap_service.add(roadmap_step)
                roadmap[index] = roadmap_step
                step_by_depth[roadmap_step.depth] = roadmap_step
                prev_id = roadmap_step.id

            await self.__save_choices(step_by_depth, raw_choices, step=step)

        return roadmap

    async def __save_choices(
        self,
        step_by_depth: dict[int, Roadmap],
        raw_choices: dict[int, list[dict]],
        *,
        step: TransactionFactory,
    ) -> None:
        """Материализует варианты выбора в roadmap_choices.

        ``next_roadmap_id`` проставляет код, а не LLM: у истинного варианта это
        следующий шаг спайна (depth+1), у форков — NULL до момента выбора.
        """
        if not self._roadmap_choice_service:
            return
        for depth, choices in raw_choices.items():
            roadmap_step = step_by_depth[depth]
            normalized = self.__normalize_choices(choices)
            next_true_step = step_by_depth.get(depth + 1)
            for order, choice in enumerate(normalized, start=1):
                next_roadmap_id = (
                    next_true_step.id
                    if choice["is_true"] and next_true_step is not None
                    else None
                )
                await self._roadmap_choice_service.add(
                    RoadmapChoice(
                        id=None,
                        created_at=None,
                        updated_at=None,
                        roadmap_id=roadmap_step.id,
                        order=order,
                        text=choice["text"],
                        is_true=choice["is_true"],
                        branch_direction=choice["branch_direction"],
                        next_roadmap_id=next_roadmap_id,
                    )
                )

    @staticmethod
    def __normalize_choices(choices: list[dict]) -> list[dict]:
        """Оставляет непустые варианты и гарантирует ровно один is_true."""
        result: list[dict] = []
        for choice in choices or []:
            text = (choice.get("text") or "").strip()
            if not text:
                continue
            result.append(
                {
                    "text": text,
                    "is_true": bool(choice.get("is_true")),
                    "branch_direction": (
                        (choice.get("branch_direction") or "").strip() or None
                    ),
                }
            )
        if not result:
            return result
        true_indexes = [i for i, c in enumerate(result) if c["is_true"]]
        if len(true_indexes) == 1:
            return result
        if true_indexes:
            # Несколько истинных — оставляем первый, остальные делаем форками.
            for i in true_indexes[1:]:
                result[i]["is_true"] = False
            return result
        # Ни одного истинного — назначаем первый (спайн должен продолжаться).
        result[0]["is_true"] = True
        return result

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

    @staticmethod
    def __choice_instructions(interactive: bool) -> str:
        if not interactive:
            return ""
        return (
            "The story is interactive: place 1-3 player choice points at genuine decision moments "
            "(usually around beats 4-6), not on every step. A choice point is a step whose target_choice "
            "is true; it ends with the player picking one of several options.\n"
            "For such steps also specify:\n"
            "9. target_choice - boolean, true if this step ends with a player choice, false otherwise.\n"
            "10. choice_stakes - when target_choice is true: a short phrase describing what the choice is about "
            "and what is at stake (empty string otherwise).\n"
            "11. choices - when target_choice is true: 2-4 options the player can pick. Each option has:\n"
            "    - text - the option label (what the player decides to do), short and concrete;\n"
            "    - is_true - boolean. EXACTLY ONE option must have is_true=true: this is the TRUE branch that "
            "continues into the NEXT step of this roadmap list. All other options are alternative branches.\n"
            "    - branch_direction - for options with is_true=false: a 1-2 sentence premise of what happens if the "
            "player picks it — a distinct, self-contained continuation that leads to its own ending. These alternative "
            "branches are NOT part of this roadmap list and will be generated separately; describe them concretely "
            "enough to be generated later. For the is_true option, branch_direction is an empty string.\n"
        )

    @staticmethod
    def __schema(interactive: bool) -> str:
        if not interactive:
            return (
                "{\n"
                '  "roadmap": [\n'
                "    {\n"
                '      "title": string,\n'
                '      "event": string,\n'
                '      "conflict": string,\n'
                '      "change": string,\n'
                '      "scenes_count": integer,\n'
                '      "location_slug": string,\n'
                '      "time_of_day": string,\n'
                '      "day": integer\n'
                "    }\n"
                "  ]\n"
                "}\n"
            )
        return (
            "{\n"
            '  "roadmap": [\n'
            "    {\n"
            '      "title": string,\n'
            '      "event": string,\n'
            '      "conflict": string,\n'
            '      "change": string,\n'
            '      "scenes_count": integer,\n'
            '      "location_slug": string,\n'
            '      "time_of_day": string,\n'
            '      "day": integer,\n'
            '      "target_choice": boolean,\n'
            '      "choice_stakes": string,\n'
            '      "choices": [\n'
            "        {\n"
            '          "text": string,\n'
            '          "is_true": boolean,\n'
            '          "branch_direction": string\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

    def __create_prompt(
        self,
        novel: Novel,
        characters: list[Character],
        background_tags: BackgroundTags | None,
    ) -> list[dict]:
        interactive = novel.mode == NovelMode.INTERACTIVE

        story_shape = (
            "a sequence of steps that make up a linear story with no branches and no player choices."
            if not interactive
            else "a sequence of steps that make up the TRUE branch of an interactive story. "
            "A few steps end with a meaningful player choice that forks the story."
        )
        system_prompt = {
            "role": "system",
            "content": (
                "You are a screenwriter for interactive visual novels. "
                "Based on the description of the story and its tone, create a plot roadmap — "
                f"{story_shape} "
                "Decide the number of steps yourself based on the scale of the story — usually 8 to 12; "
                "the more steps, the richer the story, but each step must move the plot forward "
                "rather than repeat the previous one. "
                "For each step, specify:\n"
                "1. title - a short title for the step.\n"
                "2. event - ONE completed event/beat that happens in this step; "
                "do not stretch the step over a whole arc — it should fit into 1–2 scenes.\n"
                "3. conflict - what makes this event hard for the protagonist: an obstacle, a contradiction, "
                "a risk, or what is at stake; the scene must be able to dramatize it.\n"
                "4. change - what changes for the protagonist by the end of the step: a decision, a feeling, "
                "or a shift in a relationship; one concrete consequence.\n"
                "5. scenes_count - 1 or 2 for a regular step; the final step and steps with a character's "
                "resolution may have 2 or 3. Use 2/3 only if each scene has its own "
                "beat, otherwise the scene will replay the previous one.\n"
                "6. location_slug - the slug of the location where the step takes place, ONLY from the location list "
                "(empty string if there is no list).\n"
                "7. time_of_day - the slug of the step's time of day, ONLY from the time-of-day list "
                "(empty string if there is no list).\n"
                "8. day - the story day number: an integer from 1, non-decreasing between steps; "
                "if the step takes place on the same day as the previous one, use the same number.\n"
                "The story structure is Harmon's story circle of 8 beats. Keep this order; "
                "do not rearrange or skip beats:\n"
                "1. Ordinary world — the protagonist in their ordinary life; convey their "
                "dissatisfaction or desire so that there is a reason to change.\n"
                "2. Need — the protagonist's concrete goal/desire that sets the direction of the whole story; "
                "it is also the through-line from the story description (a mystery, a goal, coming home, "
                "an internal conflict) that you must not drop before the finale.\n"
                "3. Go — an event knocks the protagonist out of ordinary life into an unfamiliar situation (the inciting event).\n"
                "4. Search — the protagonist tries to reach the goal, hits obstacles, forms relationships. "
                "Around the middle — a turn that changes the stakes.\n"
                "5. Find — the protagonist gets what they wanted, but in an unexpected or imperfect form.\n"
                "6. Take — the find must be paid for: a loss, a conflict, a consequence. This is a real "
                "obstacle/threat of failure before the climax — do not lead straight to it.\n"
                "7. Return — the protagonist returns to the familiar situation, but changed; "
                "the key event (a confession, a decision, a performance) plays out here.\n"
                "8. Change — the final state of the protagonist/world and the story's takeaway; a resolution, "
                "not a cliffhanger cut on the eve.\n"
                "Spread the beats across steps: 8 beats → 8–12 steps. The first and last beats usually take one step each; "
                "beats 4–6 can stretch over 2 steps. For significant characters (ally, rival, "
                "love interest) carry a mini-arc within these beats and resolve it by beats 7–8, "
                "not by appearing in a single scene.\n"
                "Track when each significant character first enters the story. The first time a significant "
                "character appears, dedicate a step to establishing the meeting: where and how the protagonist "
                "meets them and what makes them start interacting. Do not write a step whose event already assumes "
                "an established relationship (someone already teaching, helping, or being close to the protagonist) "
                "unless an earlier step introduced them and set up that interaction. Treat the story premise "
                "(a lesson, friendship, romance) as a goal to build toward across the arc, not as the starting "
                "state of its first related scene.\n"
                "Spread the action across place and time: adjacent steps may stay in the same location "
                "when the story flows naturally there; change location when the plot requires it "
                "(a move, a new activity, a new beat), not for the sake of variety. "
                "Every scene within a step must match the step's place and day.\n"
                "Build event/conflict/change only on the characters from the list below; do not mention in "
                "event, conflict, or change characters who are not in the list (even if they exist in the "
                "universe) — scenes with such characters will not pass validation and will be regenerated.\n"
                + self.__choice_instructions(interactive)
                + "Answer STRICTLY as JSON matching this schema:\n"
                + self.__schema(interactive)
            ),
        }
        user_content = (
            f"Title: {novel.title}\n"
            f"Description: {novel.description}\n"
            f"Narrative tone: {novel.tone}"
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
                    f"\n\nProtagonist: {protagonist.name} — the protagonist, through whose eyes the story is told. "
                    f"Their arc: {protagonist.arc}. "
                    "Build the plot around the protagonist: their goals, decisions, internal conflicts, and relationships."
                )
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

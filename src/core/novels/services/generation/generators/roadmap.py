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
from src.core.novels.services.generation.prompts.text import (
    RUSSIAN_OUTPUT_NOTE,
    parse_day,
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
            if day is None or (prev_day is not None and day < prev_day):
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
                "You are a screenwriter for interactive visual novels. "
                "Based on the description of the story and its tone, create a plot roadmap — "
                "a sequence of steps that make up a linear story with no branches and no player choices. "
                "Decide the number of steps yourself based on the scale of the story — usually 8 to 12; "
                "the more steps, the richer the story, but each step must move the plot forward "
                "rather than repeat the previous one. "
                "For each step, specify:\n"
                "1. title - a short title for the step.\n"
                "2. goal - ONE completed event/beat that happens in this step; "
                "do not stretch the step over a whole arc — it should fit into 1–2 scenes.\n"
                "3. scenes_count - 1 or 2 for a regular step; the final step and steps with a character's "
                "resolution may have 2 or 3. Use 2/3 only if each scene has its own "
                "beat, otherwise the scene will replay the previous one.\n"
                "4. location_slug - the slug of the location where the step takes place, ONLY from the location list "
                "(empty string if there is no list).\n"
                "5. time_of_day - the slug of the step's time of day, ONLY from the time-of-day list "
                "(empty string if there is no list).\n"
                "6. day - the story day number: an integer from 1, non-decreasing between steps; "
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
                "Spread the action across place and time: do not keep the whole story in one location "
                "unless the plot requires it; two adjacent steps must not take place in the same location "
                "without a plot reason. Every scene within a step must match the step's place and day.\n"
                "Build goal only on the characters from the list below; do not mention in goal characters "
                "who are not in the list (even if they exist in the universe) — scenes with such "
                "characters will not pass validation and will be regenerated.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
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

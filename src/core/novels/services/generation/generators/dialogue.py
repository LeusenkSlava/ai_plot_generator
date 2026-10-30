import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    DialogueLine,
    Scene,
)
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.assets import (
    LineAssets,
    ResolvedAssets,
    SceneAssets,
    SceneAssetService,
    _short,
)
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.generators.dialogue_repair import (
    DefectKind,
    DialogueDefect,
    DialogueRepairService,
)
from src.core.novels.services.generation.generators.story_context import (
    extract_used_phrases,
)
from src.core.novels.services.generation.prompts.cast import (
    find_protagonist,
    render_cast,
)
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)

PREVIOUS_LINE_MAX_CHARS = 300


class DialogueGenerator(BaseGenerator):
    """Генерация диалога: сущности → ассеты → промпт → LLM → сохранение."""

    def __init__(
        self,
        novel_service: NovelService,
        scene_service: SceneService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        scene_assets: SceneAssetService,
        generator: GeneratorProtocol,
        reasoning_effort: str | None = None,
        think: bool = True,
        temperature: float | None = None,
        repair: DialogueRepairService | None = None,
        max_validation_retries: int = 3,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._scene_assets = scene_assets
        self._scene_service = scene_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service
        self._reasoning_effort = reasoning_effort
        self._think = think
        self._temperature = temperature
        self._repair = repair or DialogueRepairService(
            generator=generator, scene_assets=scene_assets
        )
        self._max_validation_retries = max_validation_retries

    async def generate(
        self,
        scene_id: int,
        previous_lines: list[DialogueLine] | None = None,
        story_context: str | None = None,
        all_lines: list[DialogueLine] | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> list[DialogueLine]:
        """Генерация диалога.

        Чтение состояния и запись реплик — отдельные короткие транзакции; LLM и
        Codex-подбор ассетов идут между ними и не держат соединение Postgres.
        """
        # 1) Read-фаза: короткая транзакция.
        async with step():
            scene = await self._scene_service.get(scene_id)
            if not scene:
                raise GenerationError(f"Scene with id {scene_id} not found")

            roadmap = await self._roadmap_service.get(scene.roadmap_id)
            if not roadmap:
                raise GenerationError(f"Roadmap with id {scene.roadmap_id} not found")

            characters, all_characters = await self._scene_cast(scene, roadmap.novel_id)
            if not characters:
                raise GenerationError(f"No characters found for novel {roadmap.novel_id}")

            novel = await self._novel_service.get(roadmap.novel_id)

            last_outfits = await self._dialogue_line_service.last_outfit_per_character(
                roadmap.novel_id
            )

        # 2) LLM-фаза: Codex (HTTP) + генерация/ремонт — без транзакции.
        characters_by_name = {character.name: character for character in characters}
        protagonist = find_protagonist(characters)

        assets = await self._scene_assets.load_assets(
            novel.universe_id if novel else None, all_characters
        )
        current_outfits = self._scene_assets.current_outfits(
            characters, assets, last_outfits
        )
        used_phrases = extract_used_phrases(
            [line.text for line in (all_lines or [])],
            [c.name for c in all_characters],
        )

        base_prompt = self.__create_prompt(
            scene,
            characters,
            all_characters,
            protagonist,
            assets,
            previous_lines or [],
            story_context,
            current_outfits,
            used_phrases,
        )

        valid_names = [c.name for c in characters]
        remaining_retries = self._max_validation_retries
        prompt = base_prompt
        last_reason: str | None = None
        lines_data: list[dict] | None = None
        while True:
            data = await self._generate(
                prompt,
                think=self._think,
                reasoning_effort=self._reasoning_effort,
                temperature=self._temperature,
            )
            repair_result = await self._repair.repair_lines(
                data.get("dialogue_lines") or [], valid_names, previous_lines or []
            )
            if not repair_result.has_unfixable:
                lines_data = repair_result.lines_data
                break

            last_reason = self._describe_defects(repair_result.unfixable)
            if remaining_retries <= 0:
                break
            remaining_retries -= 1
            prompt = [*base_prompt, self.__retry_message(last_reason)]

        if lines_data is None:
            raise GenerationError(
                "DialogueGenerator: не удалось получить валидный диалог после "
                f"ретраев: {last_reason or 'неизвестная ошибка'}"
            )

        # Фаза 1: запросы на подбор фона/спрайта/одежды/эмоции по тегам от LLM
        prepared: list[tuple[Character, dict, LineAssets]] = []
        for item in lines_data:
            character = characters_by_name.get(item["character_name"])
            if not character:
                # Не должно случаться после ремонта — но на всякий случай явный guard.
                raise GenerationError(
                    f"Generator referenced unknown character '{item['character_name']}'"
                )
            prepared.append(
                (
                    character,
                    item,
                    self._scene_assets.prepare_line(item, character, assets),
                )
            )

        # Фаза 2: подбираем фон/эмоцию/спрайт/одежду через Codex (параллельно)
        resolved = await self._scene_assets.match_assets(
            prepared, assets, novel.universe_id if novel else None
        )

        # Фаза 2.5: если наряд резолвился, а эмоция нет (LLM выдумал emotion-тег),
        # перевыбираем эмоцию заново одним дешёвым запросом — без перегенерации сцены.
        resolved = await self._repair.repair_tags(
            prepared, resolved, assets, novel.universe_id if novel else None
        )

        # 3) Write-фаза: короткая транзакция только на запись. order и
        # is_final_for_scene считаются по финальному списку (после дедупа/отбрасывания).
        dialogue_lines = []
        last_index = len(lines_data) - 1
        async with step():
            for index, (character, item, _) in enumerate(prepared):
                assets_picked: ResolvedAssets = resolved[index]
                dialogue_line = DialogueLine(
                    id=None,
                    created_at=None,
                    updated_at=None,
                    novel_id=roadmap.novel_id,
                    scene_id=scene.id,
                    character_id=character.id,
                    order=index + 1,
                    text=item["text"],
                    is_final_for_scene=index == last_index,
                    is_thought=(
                        bool(item.get("is_thought", False))
                        if character.is_protagonist
                        else False
                    ),
                    background_asset_key=assets_picked.background_asset_key,
                    sound_asset_key=assets_picked.sound_asset_key,
                    sprite_asset_key=assets_picked.sprite_asset_key,
                    outfit_asset_key=assets_picked.outfit_asset_key,
                    emotion_asset_key=assets_picked.emotion_asset_key,
                )
                dialogue_line = await self._dialogue_line_service.add(dialogue_line)
                dialogue_lines.append(dialogue_line)

        return dialogue_lines

    async def _scene_cast(
        self, scene: Scene, novel_id: int
    ) -> tuple[list[Character], list[Character]]:
        """Персонажи, присутствующие в сцене, и весь каст новеллы.

        Список «кто в сцене» формирует SceneGenerator (scene.character_ids) по месту/времени
        шага. Если список пуст (старая сцена без списка), возвращаем весь каст — обратная
        совместимость с уже сгенерированными сценами. Весь каст нужен отдельно, чтобы
        подписывать имена в «последних репликах» даже для персонажей не из текущей сцены.
        """
        all_characters = await self._character_service.list_by_novel(novel_id) or []
        if not scene.character_ids:
            return all_characters, all_characters
        ids = set(scene.character_ids)
        return [c for c in all_characters if c.id in ids], all_characters

    @staticmethod
    def _describe_defects(defects: list[DialogueDefect]) -> str:
        """Сводит неисправимые дефекты к человекочитаемой причине ретрая."""
        parts: list[str] = []
        for d in defects:
            if d.kind is DefectKind.NO_LINES:
                parts.append("no dialogue lines returned")
            elif d.kind is DefectKind.UNKNOWN_CHARACTER:
                parts.append(f"unknown character name at line {d.line_index}")
            elif d.kind is DefectKind.TRUNCATED_END:
                parts.append(f"last line cut off mid-sentence at line {d.line_index}")
            else:
                parts.append(d.kind.value)
        return "; ".join(parts) or "unknown error"

    @staticmethod
    def __retry_message(reason: str) -> dict:
        """Дополнительное user-сообщение с требованием вернуть валидный JSON."""
        return {
            "role": "user",
            "content": (
                "The dialogue you returned is invalid and could not be repaired "
                "automatically. Return a completely new dialogue as JSON matching the "
                "original schema. Use ONLY the character names from the scene "
                "participants list, give every line non-empty text, and do not cut the "
                "last line off mid-sentence.\n"
                f"Reason: {reason}"
            ),
        }

    def __create_prompt(
        self,
        scene: Scene,
        characters: list[Character],
        all_characters: list[Character],
        protagonist: Character | None,
        assets: SceneAssets,
        previous_lines: list[DialogueLine],
        story_context: str | None,
        current_outfits: str,
        used_phrases: list[str],
    ) -> list[dict]:
        # Полный каст в фиксированном порядке — стабильная голова промпта для кэша.
        cast = render_cast(all_characters)
        scene_participants = ", ".join(c.name for c in characters)

        system_prompt = {
            "role": "system",
            "content": (
                "You are a screenwriter for interactive visual novels. "
                "Based on the description of the scene and the list of characters, write the dialogue that takes place in it. "
                "Write lines only for the characters listed in the «Scene participants» block; "
                "the other characters of the novel do not appear or speak in this scene. "
                "Decide the number of lines yourself based on the content of the scene — usually 8 to 16, "
                "but no fewer than 6. Do not cut the scene off mid-sentence: bring the scene's key conversation "
                "to a logical point instead of cutting it on someone else's hook line. "
                "Do not end the scene with a concluding thought or a moral that spells out what was already shown: "
                "the scene's final line should leave a concrete detail, action, or line, "
                "not an interpretation; avoid turns of phrase like «кажется», «может», «наверное», «это и называется». "
                "Do not summarize the climax (a performance, a confession, a decisive act) as an outcome: "
                "show it beat by beat — at least one crisis moment within the event and its resolution, "
                "before it concludes. "
                "The story is linear: do not offer the player any choices.\n"
                "For each line, specify:\n"
                "1. character_name - the name of the speaking character, exactly as in the list.\n"
                "2. text - the text of the line.\n"
                "3. is_thought - boolean. True if the protagonist's line is their inner thoughts "
                "(not spoken aloud, shown as an inner monologue); for speech out loud and for "
                "all other characters it is always false.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "dialogue_lines": [
                    {
                      "character_name": string,
                      "text": string,
                      "is_thought": boolean
                    }
                  ]
                }
                """
            ),
        }
        if protagonist:
            system_prompt["content"] += (
                f"\nThe protagonist is {protagonist.name}. The story is told from their point of view, "
                "so build the dialogue around their perception, goals, and decisions. "
                "They have no sprite or emotions on screen: for their lines do not specify an outfit or emotions. "
                "Their lines can be speech out loud (is_thought=false) or inner thoughts "
                "(is_thought=true) — use inner thoughts to convey their feelings and motives."
            )
        # Сначала неизменное для новеллы (персонажи, каталог), потом меняющееся:
        # так работает кеш префикса у провайдера
        user_content = f"Novel characters:\n{cast}"
        if assets:
            system_prompt["content"] += (
                "\nFor the visual of each line, pick assets ONLY from the catalog, "
                "specifying slugs and tags exactly as in the catalog, and add these fields to the line object:\n"
                "- background_base_tag - ONE location tag from the location list that fits the scene's place "
                "(usually one for the whole scene; change it only if the action moves to another place);\n"
                "- background_modifier_tags - a list of 0 or more modifier tags from the modifier list "
                "(time of day, inside/outside, light, people) matching the scene's time and setting;\n"
                "- outfit_tag - ONE outfit style tag from the speaker's outfits;\n"
                "- emotion_base_tag - ONE main emotion tag from the base emotions of the chosen outfit, "
                "matching the text of the line;\n"
                "- emotion_modifier_tags - a list of 0 or more emotion modifier tags "
                "from the modifiers of the chosen outfit.\n"
                "Pick the outfit first, then choose the emotions ONLY from the emotions "
                "listed under that chosen outfit.\n"
                "For the protagonist's lines (no sprite), set null for outfit_tag and "
                "emotion_base_tag and an empty list [] for emotion_modifier_tags; "
                "specify the background (background_base_tag and background_modifier_tags) as for other lines.\n"
                "If there is no suitable asset, set null; for emotion_modifier_tags set an empty list [].\n"
                "A character's outfit does not change between lines and scenes: keep using their current "
                "outfit_tag until the plot clearly has them change clothes."
            )
            user_content += f"\n\nAsset catalog:\n{self._scene_assets.assets_catalog(all_characters, assets)}"
        if story_context:
            user_content += (
                "\n\nStory so far (do not contradict it; "
                "characters are dressed as stated there until the plot has them change clothes):\n"
                f"{story_context}"
            )
        if current_outfits:
            user_content += f"\n\nCurrent character outfits:\n{current_outfits}"
        if previous_lines:
            names = {character.id: character.name for character in all_characters}
            recap = "\n".join(
                f"{names.get(line.character_id, '?')}"
                f"{' (thoughts)' if line.is_thought else ''}: "
                f"{_short(line.text, PREVIOUS_LINE_MAX_CHARS)}"
                for line in previous_lines
            )
            user_content += f"\n\nLast lines of the previous scene (continue the story, do not repeat them):\n{recap}"
        if used_phrases:
            user_content += (
                "\n\nPhrases already used in the story (do not repeat them verbatim):\n"
                + "\n".join(f"- {p}" for p in used_phrases)
            )
        user_content += (
            f"\n\nScene: {scene.title}\nScene description: {scene.description}"
        )
        user_content += f"\nScene participants: {scene_participants}"
        system_prompt["content"] += f"\n{RUSSIAN_OUTPUT_NOTE}"

        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import (
    Character,
    DialogueLine,
    LineKind,
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
    SceneAssetService,
)
from src.core.novels.services.generation.context import DialogueContextLoader
from src.core.novels.services.generation.generators.base import BaseGenerator
from src.core.novels.services.generation.generators.dialogue_repair import (
    DefectKind,
    DialogueDefect,
    DialogueRepairService,
)
from src.core.novels.services.generation.prompts.cast import find_protagonist
from src.core.novels.services.generation.prompts.catalog import PromptCatalog
from src.core.novels.services.generation.prompts.dialogue import (
    DialoguePromptBuilder,
    DialoguePromptContext,
)
from src.core.novels.services.generation.story_state import extract_used_phrases
from src.core.novels.services.generation.transactions import (
    TransactionFactory,
    noop_step,
)

logger = logging.getLogger(__name__)


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
        *, prompt_catalog: PromptCatalog,
    ):
        super().__init__(generator)
        self._scene_assets = scene_assets
        self._dialogue_line_service = dialogue_line_service
        self._reasoning_effort = reasoning_effort
        self._think = think
        self._temperature = temperature
        self._repair = repair or DialogueRepairService(
            generator=generator, scene_assets=scene_assets
        )
        self._max_validation_retries = max_validation_retries
        self._prompt_builder = DialoguePromptBuilder(scene_assets)
        self._context_loader = DialogueContextLoader(
            novel_service=novel_service,
            scene_service=scene_service,
            roadmap_service=roadmap_service,
            character_service=character_service,
            dialogue_line_service=dialogue_line_service,
            prompt_catalog=prompt_catalog,
        )

    async def generate(
        self,
        scene_id: int,
        previous_lines: list[DialogueLine] | None = None,
        story_context: str | None = None,
        all_lines: list[DialogueLine] | None = None,
        previous_scene: Scene | None = None,
        *,
        step: TransactionFactory = noop_step,
    ) -> list[DialogueLine]:
        """Генерация диалога.

        Чтение состояния и запись реплик — отдельные короткие транзакции; LLM и
        Codex-подбор ассетов идут между ними и не держат соединение Postgres.
        """
        # 1) Read-фаза: короткая транзакция.
        async with step():
            read = await self._context_loader.load(scene_id)
            scene = read.scene
            roadmap = read.roadmap
            novel = read.novel
            characters = read.characters
            all_characters = read.all_characters
            last_outfits = read.last_outfits
            template = read.template

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

        base_prompt = self._prompt_builder.build(
            template,
            DialoguePromptContext(
                scene=scene,
                roadmap=roadmap,
                characters=characters,
                all_characters=all_characters,
                protagonist=protagonist,
                assets=assets,
                previous_lines=previous_lines or [],
                story_context=story_context,
                current_outfits=current_outfits,
                used_phrases=used_phrases,
                previous_scene=previous_scene,
                scene_position=read.scene_position,
                scenes_count=read.scenes_count,
            ),
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

        # Фаза 1: запросы на подбор спрайта/одежды/эмоции по тегам от LLM.
        # Фон в реплику не входит: он резолвится один раз на всю сцену.
        prepared: list[tuple[Character | None, dict, LineAssets]] = []
        for item in lines_data:
            # После repair_lines каждый ``kind`` уже каноничен (иначе repair
            # отдал бы дефект UNKNOWN_KIND и генерация ушла бы в ретрай).
            kind = LineKind(item["kind"])
            if kind is LineKind.NARRATION:
                # Narration — ремарка без говорящего: спрайта/наряда/эмоции нет.
                character = None
            else:
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

        # Фаза 2: фон — по сегментам сцены (открывающий + background_changes);
        # спрайт/эмоция/одежда — через Codex (параллельно).
        raw_background_tags = data.get("background_modifier_tags")
        background_modifier_tags = (
            raw_background_tags if isinstance(raw_background_tags, list) else []
        )
        background_changes = self._scene_assets.normalize_background_changes(
            data.get("background_changes"), len(lines_data)
        )
        segments = self._scene_assets.anchor_background_tags_per_line(
            scene, background_modifier_tags, background_changes, len(lines_data), assets
        )
        line_background_tags = [segment.tags for segment in segments]
        resolved = await self._scene_assets.match_assets(
            prepared,
            assets,
            novel.universe_id if novel else None,
            line_background_tags=line_background_tags,
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
                kind = LineKind(item["kind"])
                # thought значим только для протагониста; narration — всегда без персонажа.
                if kind is LineKind.THOUGHT and (
                    character is None or not character.is_protagonist
                ):
                    kind = LineKind.SPEECH
                dialogue_line = DialogueLine(
                    id=None,
                    created_at=None,
                    updated_at=None,
                    novel_id=roadmap.novel_id,
                    scene_id=scene.id,
                    character_id=character.id if character else None,
                    order=index + 1,
                    text=item["text"],
                    is_final_for_scene=index == last_index,
                    kind=kind,
                    background_asset_key=assets_picked.background_asset_key,
                    sound_asset_key=assets_picked.sound_asset_key,
                    sprite_asset_key=assets_picked.sprite_asset_key,
                    location_slug=segments[index].location_slug,
                    outfit_tag=assets_picked.outfit_tag,
                    outfit_asset_key=assets_picked.outfit_asset_key,
                    emotion_asset_key=assets_picked.emotion_asset_key,
                )
                dialogue_line = await self._dialogue_line_service.add(dialogue_line)
                dialogue_lines.append(dialogue_line)

        return dialogue_lines

    @staticmethod
    def _describe_defects(defects: list[DialogueDefect]) -> str:
        """Сводит неисправимые дефекты к человекочитаемой причине ретрая."""
        parts: list[str] = []
        for d in defects:
            if d.kind is DefectKind.NO_LINES:
                parts.append("no dialogue lines returned")
            elif d.kind is DefectKind.UNKNOWN_CHARACTER:
                parts.append(f"unknown character name at line {d.line_index}")
            elif d.kind is DefectKind.UNKNOWN_KIND:
                parts.append(f"unknown line kind at line {d.line_index}")
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

"""Сервис ассетов сцены: загрузка, каталог и резолв фонов/нарядов/эмоций.

Собирает из Codex всё, что нужно генератору диалога для привязки реплик к
визуальным ассетам: теги фонов вселенной и каталог нарядов персонажей (с
эмоциями на каждом наряде). Затем резолвит выбор LLM (теги) в конкретные
asset_key через подбор визуала в Codex.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    BackgroundTags,
    Emotion,
    OutfitWithEmotions,
    Tag,
    TagKind,
    TagType,
)
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.models import Character

logger = logging.getLogger(__name__)

SPRITE_DESCRIPTION_MAX_CHARS = 100


def _short(text: str, limit: int = SPRITE_DESCRIPTION_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _emotion_tags_by_kind(emotions: list[Emotion]) -> tuple[list[Tag], list[Tag]]:
    """Разделяет emotion-теги наряда на base и modifiers."""
    base: list[Tag] = []
    modifiers: list[Tag] = []
    for emotion in emotions:
        for tag in emotion.tags:
            if tag.type != TagType.EMOTION:
                continue
            if tag.kind == TagKind.MODIFIER:
                modifiers.append(tag)
            else:
                base.append(tag)
    return base, modifiers


@dataclass
class SceneAssets:
    """Ассеты из Codex, доступные для сцены: теги фонов вселенной и наряды персонажей."""

    # теги фонов вселенной (базовые локации + уточнения); фон подбирается по ним
    background_tags: BackgroundTags | None = None
    # codex_character_id -> наряды с доступными на них эмоциями
    outfits: dict[int, list[OutfitWithEmotions]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.background_tags or self.outfits)


@dataclass
class LineAssets:
    """Подготовленные по реплике ассеты: теги фона и запросы подбора наряда/эмоции."""

    # теги фона (ровно один base + 0..N modifier), выбранные LLM
    background_tags: list[str] | None = None
    emotion_tags: list[str] | None = None
    outfit_tag: str | None = None


@dataclass
class ResolvedAssets:
    """Итоговые asset_key реплики после подбора визуала."""

    background_asset_key: str | None = None
    sprite_asset_key: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


class SceneAssetService:
    """Загрузка и подбор визуальных ассетов сцены через Codex."""

    def __init__(self, codex_service: CodexService):
        self._codex_service = codex_service

    async def load_assets(
        self, universe_id: int | None, characters: list[Character]
    ) -> SceneAssets:
        assets = SceneAssets()
        # Без вселенной в Codex не ходим
        if universe_id is None:
            return assets
        try:
            codex_ids = [
                c.codex_character_id
                for c in characters
                if not c.is_protagonist and c.codex_character_id is not None
            ]
            assets.background_tags, assets.outfits = await asyncio.gather(
                self._codex_service.get_background_tags(universe_id),
                self._codex_service.get_outfits_with_emotions_batch(codex_ids),
            )
        except Exception as e:
            raise GenerationError(f"Codex assets request failed: {e}") from e
        return assets

    @staticmethod
    def prepare_line(
        item: dict, character: Character, assets: SceneAssets
    ) -> LineAssets:
        """Переводит выбранные LLM теги в запросы подбора ассетов Codex."""
        line = LineAssets()
        if not assets:
            return line

        base_tag = item.get("background_base_tag")
        if base_tag:
            modifier_tags = item.get("background_modifier_tags") or []
            line.background_tags = [base_tag, *modifier_tags]

        if character.is_protagonist:
            # Протагонист на экране не показывается: наряд/эмоция не нужны.
            return line

        base_tag = item.get("emotion_base_tag")
        if base_tag:
            modifier_tags = item.get("emotion_modifier_tags") or []
            line.emotion_tags = [base_tag, *modifier_tags]

        line.outfit_tag = item.get("outfit_tag")

        return line

    @staticmethod
    def emotions_for_outfit(
        assets: SceneAssets, codex_character_id: int | None, outfit_tag: str
    ) -> tuple[list[str], list[str]]:
        """Валидные emotion-слаги наряда персонажа: (base, modifiers).

        Слаги объединяются по всем сущностям-нарядам с одинаковым style-тегом —
        именно так тег одежды резолвится в match_visual.
        """
        if codex_character_id is None:
            return [], []
        base: set[str] = set()
        modifiers: set[str] = set()
        for entry in assets.outfits.get(codex_character_id, []):
            entry_tag = next(
                (t.slug for t in entry.outfit.tags if t.type == TagType.OUTFIT_STYLE),
                None,
            )
            if entry_tag != outfit_tag:
                continue
            base_tags, modifier_tags = _emotion_tags_by_kind(entry.emotions)
            base.update(t.slug for t in base_tags)
            modifiers.update(t.slug for t in modifier_tags)
        return sorted(base), sorted(modifiers)

    async def match_emotion_asset(
        self, codex_character_id: int, outfit_tag: str, emotion_tags: list[str]
    ) -> str | None:
        """Подбирает только asset_key эмоции по тегу одежды и эмоциям."""
        try:
            visual = await self._codex_service.match_visual(
                codex_character_id, outfit_tag, emotion_tags
            )
        except CodexUnavailableError as e:
            logger.warning(
                f"SceneAssetService: emotion match failed for "
                f"character={codex_character_id} outfit={outfit_tag} "
                f"emotions={emotion_tags}: {e}"
            )
            return None
        if visual and visual.emotion_asset_key:
            return visual.emotion_asset_key
        return None

    async def match_assets(
        self,
        prepared: list[tuple[Character, dict, LineAssets]],
        assets: SceneAssets,
        universe_id: int | None,
    ) -> list[ResolvedAssets]:
        """Подбирает фон по тегам и визуал (спрайт+наряд+эмоцию) через Codex."""

        async def resolve(character: Character, line: LineAssets) -> ResolvedAssets:
            result = ResolvedAssets()

            # Фон подбирается по тегам-смыслам через Codex (как и визуал).
            if universe_id is not None and line.background_tags:
                try:
                    background = await self._codex_service.match_background(
                        universe_id, line.background_tags
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"SceneAssetService: background match failed for "
                        f"tags={line.background_tags}: {e}"
                    )
                    background = None
                if background:
                    result.background_asset_key = background.asset_key
                else:
                    logger.warning(
                        f"SceneAssetService: no background matched for "
                        f"tags={line.background_tags}"
                    )

            if character.is_protagonist:
                # Протагонист без спрайта — подбирать визуал не нужно.
                return result
            codex_id = character.codex_character_id

            # Спрайт + наряд + эмоция подбираются одним запросом в Codex.
            if codex_id is not None and line.outfit_tag:
                try:
                    visual = await self._codex_service.match_visual(
                        codex_id, line.outfit_tag, line.emotion_tags or []
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"SceneAssetService: visual match failed for "
                        f"{character.name} outfit={line.outfit_tag} "
                        f"emotions={line.emotion_tags}: {e}"
                    )
                    visual = None
                if visual:
                    result.sprite_asset_key = visual.sprite_asset_key
                    result.outfit_asset_key = visual.outfit_asset_key
                    result.emotion_asset_key = visual.emotion_asset_key
                else:
                    logger.warning(
                        f"SceneAssetService: no visual matched for "
                        f"{character.name} outfit={line.outfit_tag} "
                        f"emotions={line.emotion_tags}"
                    )

            return result

        return await asyncio.gather(
            *(resolve(character, line) for character, _, line in prepared)
        )

    @staticmethod
    def current_outfits(
        characters: list[Character], assets: SceneAssets, last_outfits: dict[int, str]
    ) -> str:
        """Резолв последнего наряда каждого персонажа: asset_key -> тег одежды."""
        lines: list[str] = []

        for c in characters:
            asset_key = last_outfits.get(c.id)
            if not asset_key:
                continue
            for entry in assets.outfits.get(c.codex_character_id, []):
                if entry.outfit.asset_key == asset_key:
                    tag = next(
                        (
                            t.slug
                            for t in entry.outfit.tags
                            if t.type == TagType.OUTFIT_STYLE
                        ),
                        None,
                    )
                    if tag:
                        lines.append(f"- {c.name}: outfit_tag {tag} ({entry.outfit.name})")
                    break
        return "\n".join(lines)

    @staticmethod
    def assets_catalog(characters: list[Character], assets: SceneAssets) -> str:
        lines: list[str] = []
        if assets.background_tags:
            base = (
                ", ".join(f"{t.slug}={t.name}" for t in assets.background_tags.base)
                or "-"
            )
            modifiers = (
                ", ".join(
                    f"{t.slug}={t.name}" for t in assets.background_tags.modifiers
                )
                or "-"
            )
            lines.append("Backgrounds (background_base_tag + background_modifier_tags):")
            lines.append(f"  locations (exactly one background_base_tag): {base}")
            lines.append(
                f"  modifiers (0 or more background_modifier_tags): {modifiers}"
            )
        for character in characters:
            outfits = assets.outfits.get(character.codex_character_id)
            if not outfits:
                continue
            lines.append(
                f"Outfits of character {character.name} (outfit_tag → emotions):"
            )
            for entry in outfits:
                outfit = entry.outfit
                outfit_tag = next(
                    (
                        t.slug
                        for t in outfit.tags
                        if t.type == TagType.OUTFIT_STYLE
                    ),
                    None,
                )
                base_tags, modifier_tags = _emotion_tags_by_kind(entry.emotions)
                base = ", ".join(f"{t.slug}={t.name}" for t in base_tags) or "-"
                modifiers = (
                    ", ".join(f"{t.slug}={t.name}" for t in modifier_tags) or "-"
                )
                label = f"{outfit_tag} ({outfit.name})" if outfit_tag else outfit.name
                lines.append(f"- {label}:")
                lines.append(f"    base (emotion_base_tag): {base}")
                lines.append(f"    modifiers (emotion_modifier_tags): {modifiers}")
        return "\n".join(lines)

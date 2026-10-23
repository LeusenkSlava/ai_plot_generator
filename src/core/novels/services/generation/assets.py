"""Сервис ассетов сцены: загрузка, каталог и резолв спрайтов/фонов/одежды/эмоций.

Собирает из Codex всё, что нужно генератору диалога для привязки реплик к
визуальным ассетам: теги фонов вселенной, спрайты, эмоции и наряды персонажей.
Затем резолвит выбор LLM (slug'и и теги) в конкретные asset_key.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from src.core.codex.exceptions import CodexUnavailableError
from src.core.codex.models import (
    BackgroundTags,
    EmotionTags,
    Outfit,
    Sprite,
    Tag,
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


@dataclass
class _SpriteAssets:
    sprite: Sprite
    outfits: dict[str, Outfit] = field(default_factory=dict)


@dataclass
class SceneAssets:
    """Ассеты из Codex, доступные для сцены: теги фонов вселенной и спрайты персонажей."""

    # теги фонов вселенной (базовые локации + уточнения); фон подбирается по ним
    background_tags: BackgroundTags | None = None
    # character.id -> sprite.slug -> ассеты спрайта
    sprites: dict[int, dict[str, _SpriteAssets]] = field(default_factory=dict)
    # character.id -> доступные эмоции-теги (база + модификаторы)
    emotion_tags: dict[int, EmotionTags] = field(default_factory=dict)
    # character.id -> доступные теги одежды (outfit_style)
    outfit_tags: dict[int, list[Tag]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.background_tags or self.sprites)


@dataclass
class LineAssets:
    """Подготовленные по реплике ассеты: теги фона и запросы подбора спрайта/одежды/эмоции."""

    # теги фона (ровно один base + 0..N modifier), выбранные LLM
    background_tags: list[str] | None = None
    # кандидат-спрайт, выбранный LLM; используется как подсказка для match_emotion
    sprite_id: int | None = None
    emotion_tags: list[str] | None = None
    outfit_tag: str | None = None


@dataclass
class ResolvedAssets:
    """Итоговые asset_key реплики после подбора эмоции/спрайта/одежды."""

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
            assets.background_tags = await self._codex_service.get_background_tags(
                universe_id
            )
            for character in characters:
                if character.is_protagonist:
                    # У протагониста спрайт не отображается — ассеты не грузим.
                    continue
                if character.codex_character_id is None:
                    continue
                assets.emotion_tags[character.id] = (
                    await self._codex_service.get_emotion_tags(
                        character.codex_character_id
                    )
                )
                assets.outfit_tags[character.id] = (
                    await self._codex_service.get_outfit_tags(
                        character.codex_character_id
                    )
                )
                by_sprite: dict[str, _SpriteAssets] = {}
                for sprite in await self._codex_service.get_sprites(
                    character.codex_character_id
                ):
                    outfits = await self._codex_service.get_outfits(sprite.id)
                    by_sprite[sprite.slug] = _SpriteAssets(
                        sprite=sprite,
                        outfits={o.slug: o for o in outfits},
                    )
                assets.sprites[character.id] = by_sprite
        except Exception as e:
            raise GenerationError(f"Codex assets request failed: {e}") from e
        return assets

    @staticmethod
    def prepare_line(
        item: dict, character: Character, assets: SceneAssets
    ) -> LineAssets:
        """Переводит выбранные LLM slug'и/теги в запросы подбора ассетов Codex."""
        line = LineAssets()
        if not assets:
            return line

        base_tag = item.get("background_base_tag")
        if base_tag:
            modifier_tags = item.get("background_modifier_tags") or []
            line.background_tags = [base_tag, *modifier_tags]

        if character.is_protagonist:
            # Протагонист на экране не показывается: спрайт/наряд/эмоция не нужны.
            return line

        sprite_assets = assets.sprites.get(character.id, {}).get(
            item.get("sprite_slug") or ""
        )
        if sprite_assets:
            line.sprite_id = sprite_assets.sprite.id
        elif item.get("sprite_slug"):
            logger.warning(
                f"SceneAssetService: unresolved sprite_slug for line {item!r}"
            )

        base_tag = item.get("emotion_base_tag")
        if base_tag:
            modifier_tags = item.get("emotion_modifier_tags") or []
            line.emotion_tags = [base_tag, *modifier_tags]

        line.outfit_tag = item.get("outfit_tag")

        return line

    async def match_assets(
        self,
        prepared: list[tuple[Character, dict, LineAssets]],
        assets: SceneAssets,
        universe_id: int | None,
    ) -> list[ResolvedAssets]:
        """Подбирает по тегам фон, эмоцию и одежду; финальный спрайт берёт из эмоции."""

        async def resolve(character: Character, line: LineAssets) -> ResolvedAssets:
            result = ResolvedAssets()

            # Фон подбирается по тегам-смыслам через Codex (как эмоция/одежда).
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
                # Протагонист без спрайта — подбирать эмоцию/наряд не нужно.
                return result
            codex_id = character.codex_character_id

            # 1. Эмоция. match_emotion может вернуть эмоцию на другом спрайте,
            #    поэтому спрайт берём из результата, а не из выбора LLM.
            emotion = None
            if codex_id is not None and line.emotion_tags:
                try:
                    emotion = await self._codex_service.match_emotion(
                        codex_id, line.emotion_tags, sprite_id=line.sprite_id
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"SceneAssetService: emotion match failed for "
                        f"{character.name} tags={line.emotion_tags}: {e}"
                    )
                if emotion is None:
                    logger.warning(
                        f"SceneAssetService: no emotion matched for "
                        f"{character.name} tags={line.emotion_tags}"
                    )

            # 2. Финальный спрайт: из подобранной эмоции, иначе — выбор LLM.
            final_sprite_id = emotion.sprite_id if emotion else line.sprite_id
            sprite_assets = self.sprite_assets_by_id(
                character.id, final_sprite_id, assets
            )
            if sprite_assets:
                result.sprite_asset_key = sprite_assets.sprite.asset_key

            # 3. Одежда подбирается на финальном спрайте по одному тегу-стилю.
            if final_sprite_id is not None and line.outfit_tag:
                try:
                    outfit = await self._codex_service.match_outfit(
                        final_sprite_id, line.outfit_tag
                    )
                except CodexUnavailableError as e:
                    logger.warning(
                        f"SceneAssetService: outfit match failed for "
                        f"{character.name} tag={line.outfit_tag} "
                        f"sprite={final_sprite_id}: {e}"
                    )
                    outfit = None
                if outfit:
                    result.outfit_asset_key = outfit.asset_key
                else:
                    logger.warning(
                        f"SceneAssetService: no outfit matched for "
                        f"{character.name} tag={line.outfit_tag} "
                        f"sprite={final_sprite_id}"
                    )

            # 4. Эмоция.
            if emotion:
                result.emotion_asset_key = emotion.asset_key

            return result

        return await asyncio.gather(
            *(resolve(character, line) for character, _, line in prepared)
        )

    @staticmethod
    def sprite_assets_by_id(
        character_id: int, sprite_id: int | None, assets: SceneAssets
    ) -> _SpriteAssets | None:
        if sprite_id is None:
            return None
        for sa in assets.sprites.get(character_id, {}).values():
            if sa.sprite.id == sprite_id:
                return sa
        return None

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
            for sa in assets.sprites.get(c.id, {}).values():
                for outfit in sa.outfits.values():
                    if outfit.asset_key == asset_key:
                        tag = next(
                            (
                                t.slug
                                for t in outfit.tags
                                if t.type == TagType.OUTFIT_STYLE
                            ),
                            None,
                        )
                        if tag:
                            lines.append(
                                f"- {c.name}: outfit_tag {tag} ({outfit.name})"
                            )
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
            sprites = assets.sprites.get(character.id)
            if not sprites:
                continue
            lines.append(f"Sprites (sprite_slug) of character {character.name}:")
            for slug, sa in sprites.items():
                lines.append(f"- {slug}: {_short(sa.sprite.description)}")
            tags = assets.emotion_tags.get(character.id)
            if tags:
                base = ", ".join(f"{t.slug}={t.name}" for t in tags.base) or "-"
                modifiers = (
                    ", ".join(f"{t.slug}={t.name}" for t in tags.modifiers) or "-"
                )
                lines.append(f"Emotions of character {character.name}:")
                lines.append(f"  base (emotion_base_tag): {base}")
                lines.append(f"  modifiers (emotion_modifier_tags): {modifiers}")
            outfit_tags = assets.outfit_tags.get(character.id)
            if outfit_tags:
                styles = (
                    ", ".join(f"{t.slug}={t.name}" for t in outfit_tags) or "-"
                )
                lines.append(
                    f"Outfits of character {character.name} (outfit_tag): {styles}"
                )
        return "\n".join(lines)

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
    OutfitEmotion,
    OutfitWithEmotions,
    TagKind,
    TagType,
)
from src.core.codex.services import CodexService
from src.core.novels.exceptions import GenerationError
from src.core.novels.models import Character, Scene

logger = logging.getLogger(__name__)

SPRITE_DESCRIPTION_MAX_CHARS = 100


def _short(text: str, limit: int = SPRITE_DESCRIPTION_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _split_emotions(
    emotions: list[OutfitEmotion],
) -> tuple[list[OutfitEmotion], list[OutfitEmotion]]:
    """Делит emotion-теги наряда на base и modifiers по их kind."""
    base: list[OutfitEmotion] = []
    modifiers: list[OutfitEmotion] = []
    for emotion in emotions:
        if emotion.kind == TagKind.MODIFIER:
            modifiers.append(emotion)
        else:
            base.append(emotion)
    return base, modifiers


def _clean_tags(value: object) -> list[str]:
    """Нормализует список slug-тегов: только строки, без пустых, без повторов.

    Порядок сохраняется; не-список и не-строковые элементы отбрасываются.
    """
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for tag in value:
        if isinstance(tag, str) and tag.strip() and tag.strip() not in tags:
            tags.append(tag.strip())
    return tags


@dataclass
class SceneAssets:
    """Ассеты из Codex, доступные для сцены: теги фонов вселенной и наряды персонажей."""

    # теги фонов вселенной (базовые локации + уточнения); фон подбирается по ним
    background_tags: BackgroundTags | None = None
    # codex_character_id -> style-теги одежды с доступными эмоциями
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
    sound_asset_key: str | None = None
    sprite_asset_key: str | None = None
    outfit_tag: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


@dataclass(frozen=True)
class BackgroundChange:
    """Смена фона внутри сцены: с какой реплики и на какой фон.

    ``location_slug`` — базовая локация нового сегмента (``None`` — сохранить
    текущую). ``modifiers`` — модификаторы нового сегмента.
    """

    at_line: int
    location_slug: str | None
    modifiers: list[str]


@dataclass(frozen=True)
class BackgroundSegment:
    """Фон одного сегмента сцены: базовая локация + полный набор тегов."""

    location_slug: str | None
    tags: list[str] | None


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
        item: dict, character: Character | None, assets: SceneAssets
    ) -> LineAssets:
        """Переводит выбранные LLM теги наряда/эмоции в запросы подбора ассетов.

        ``character is None`` — narration-ремарка: у неё нет спрайта/наряда/эмоции.
        Фон сюда не входит: он резолвится по сегментам сцены (см. ``match_assets``).
        """
        line = LineAssets()
        if not assets:
            return line

        if character is None or character.is_protagonist:
            # Narration / протагонист на экране не показывается: наряд/эмоция не нужны.
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

        Codex уже отдаёт по одной группе на style-тег с объединёнными эмоциями
        всех спрайтов, поэтому здесь достаточно найти группу по тегу.
        """
        if codex_character_id is None:
            return [], []
        base: set[str] = set()
        modifiers: set[str] = set()
        for entry in assets.outfits.get(codex_character_id, []):
            if entry.outfit_tag != outfit_tag:
                continue
            base_tags, modifier_tags = _split_emotions(entry.emotions)
            base.update(e.slug for e in base_tags)
            modifiers.update(e.slug for e in modifier_tags)
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

    @staticmethod
    def _background_tags(
        scene: Scene, base: str, modifiers: list[str], assets: SceneAssets
    ) -> list[str] | None:
        """Собирает ``[base, *modifiers]`` с принудительным временем суток из сцены.

        Возвращает ``None``, когда подбирать фон не из чего (нет вселенной или нет
        базовой локации).
        """
        if not assets or not assets.background_tags:
            return None
        normalized_base = (base or "").strip() or None
        if not normalized_base:
            return None

        cleaned = _clean_tags(modifiers)
        if scene.time_of_day:
            time_slugs = {
                t.slug
                for t in assets.background_tags.modifiers
                if t.type is TagType.TIME_OF_DAY
            }
            overridden = [m for m in cleaned if m in time_slugs]
            if overridden:
                logger.warning(
                    "SceneAssetService: model-supplied time-of-day tags %s are "
                    "overridden by scene.time_of_day=%r",
                    overridden,
                    scene.time_of_day,
                )
            cleaned = [m for m in cleaned if m not in time_slugs]
            if scene.time_of_day not in cleaned:
                cleaned.append(scene.time_of_day)

        return [normalized_base, *cleaned]

    @staticmethod
    def anchor_background_tags(
        scene: Scene, background_modifier_tags: list[str], assets: SceneAssets
    ) -> list[str] | None:
        """Собирает один набор тегов фона на всю сцену: база + модификаторы.

        База — ``scene.location_slug`` (задаётся шагом роадмапа и сверяется
        валидатором сцены). Модификаторы — однократный выбор LLM
        (``background_modifier_tags``) с принудительной заменой времени суток на
        ``scene.time_of_day``. Возвращает ``None``, когда подбирать фон не из чего
        (нет вселенной или нет локации).
        """
        return SceneAssetService._background_tags(
            scene, scene.location_slug or "", background_modifier_tags, assets
        )

    @staticmethod
    def normalize_background_changes(
        raw: object, line_count: int
    ) -> list[BackgroundChange]:
        """Нормализует сырые ``background_changes`` в отсортированный список ``BackgroundChange``.

        Оставляет только валидные смены: ``at_line`` — целое в ``[1, line_count]``
        без повторов; ``location_slug`` — строка или ``None``; ``background_modifier_tags``
        — список тегов (может быть пустым, если задан ``location_slug``). Результат
        отсортирован по ``at_line``; невалидные записи отбрасываются.
        """
        if not isinstance(raw, list) or line_count <= 0:
            return []
        changes: list[BackgroundChange] = []
        seen: set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            raw_line = item.get("at_line")
            if not isinstance(raw_line, (int, str)):
                continue
            try:
                at_line = int(raw_line)
            except (TypeError, ValueError):
                continue
            modifiers = _clean_tags(item.get("background_modifier_tags"))
            location = item.get("location_slug")
            location_slug = (
                location.strip()
                if isinstance(location, str) and location.strip()
                else None
            )
            if not (1 <= at_line <= line_count) or at_line in seen:
                continue
            # Пустая смена (ни модификаторов, ни локации) не меняет фон — пропускаем.
            if not modifiers and location_slug is None:
                continue
            seen.add(at_line)
            changes.append(BackgroundChange(at_line, location_slug, modifiers))
        changes.sort(key=lambda change: change.at_line)
        return changes

    @staticmethod
    def anchor_background_tags_per_line(
        scene: Scene,
        opening_modifiers: list[str],
        changes: list[BackgroundChange],
        line_count: int,
        assets: SceneAssets,
    ) -> list[BackgroundSegment]:
        """Фон каждого сегмента сцены: открывающая локация + смены по репликам.

        ``changes`` — уже нормализованный отсортированный список ``BackgroundChange``,
        где ``at_line`` — 1-базовый индекс первой реплики нового места. Смена может
        нести ``location_slug`` (новую базовую локацию из каталога; неизвестная
        локация игнорируется — остаётся текущая) и/или новые модификаторы. Возвращает
        список длиной ``line_count``; ``tags=None`` на позиции означает «фон для этой
        реплики не резолвится» (нет вселенной/локации — якоря нет вовсе).
        """
        if line_count <= 0:
            return []
        opening_base = scene.location_slug
        opening_tags = SceneAssetService._background_tags(
            scene, opening_base or "", opening_modifiers, assets
        )
        if opening_tags is None:
            return [BackgroundSegment(opening_base, None)] * line_count

        valid_bases = {
            tag.slug for tag in (assets.background_tags.base or [])
        } if assets.background_tags else set()

        per_line: list[BackgroundSegment] = []
        change_index = 0
        current_base = opening_base
        current_tags = opening_tags
        for line_index in range(1, line_count + 1):
            while change_index < len(changes) and changes[change_index].at_line <= line_index:
                change = changes[change_index]
                next_base = change.location_slug or current_base
                if next_base != current_base and next_base not in valid_bases:
                    logger.warning(
                        "SceneAssetService: unknown background location %r in "
                        "background_changes; keeping %r",
                        next_base,
                        current_base,
                    )
                    next_base = current_base
                current_base = next_base
                tags = SceneAssetService._background_tags(
                    scene, current_base or "", change.modifiers, assets
                )
                # Якорь уже проверен выше: база и ассеты есть — None невозможен.
                assert tags is not None
                current_tags = tags
                change_index += 1
            per_line.append(BackgroundSegment(current_base, list(current_tags)))
        return per_line

    async def match_scene_background(
        self, universe_id: int | None, tags: list[str] | None
    ) -> ResolvedAssets:
        """Один подбор фона на сцену (в отличие от построчного ``match_assets``)."""
        result = ResolvedAssets()
        if universe_id is None or not tags:
            return result
        try:
            background = await self._codex_service.match_background(universe_id, tags)
        except CodexUnavailableError as e:
            logger.warning(
                f"SceneAssetService: background match failed for tags={tags}: {e}"
            )
            return result
        if background:
            result.background_asset_key = background.asset_key
            result.sound_asset_key = background.sound_asset_key
        else:
            logger.warning(
                f"SceneAssetService: no background matched for tags={tags}"
            )
        return result

    async def match_assets(
        self,
        prepared: list[tuple[Character | None, dict, LineAssets]],
        assets: SceneAssets,
        universe_id: int | None,
        line_background_tags: list[list[str] | None] | None = None,
    ) -> list[ResolvedAssets]:
        """Подбирает фон (по сегментам) и визуал (спрайт+наряд+эмоцию) через Codex.

        ``line_background_tags`` — теги фона на каждую реплику (по одному списку на
        реплику; ``None`` на позиции — фон для этой реплики не резолвится). Одинаковые
        наборы резолвятся один раз и раздаются всем репликам сегмента. Если весь
        параметр ``None`` — построчный подбор для обратной совместимости (тесты и
        старые сцены).
        """
        scene_backgrounds: dict[tuple[str, ...], ResolvedAssets] = {}
        if line_background_tags is not None:
            unique: dict[tuple[str, ...], list[str]] = {}
            for tags in line_background_tags:
                if tags:
                    unique.setdefault(tuple(tags), tags)
            if unique:
                keys = list(unique)
                resolved = await asyncio.gather(
                    *(self.match_scene_background(universe_id, unique[key]) for key in keys)
                )
                scene_backgrounds = dict(zip(keys, resolved))

        async def resolve(
            character: Character | None, line: LineAssets, index: int
        ) -> ResolvedAssets:
            result = ResolvedAssets()

            if line_background_tags is not None:
                tags = line_background_tags[index]
                if tags:
                    bg_resolved = scene_backgrounds[tuple(tags)]
                    result.background_asset_key = bg_resolved.background_asset_key
                    result.sound_asset_key = bg_resolved.sound_asset_key
            elif universe_id is not None and line.background_tags:
                # Обратная совместимость: построчный подбор фона (тесты и старые сцены).
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
                    result.sound_asset_key = background.sound_asset_key
                else:
                    logger.warning(
                        f"SceneAssetService: no background matched for "
                        f"tags={line.background_tags}"
                    )

            if character is None or character.is_protagonist:
                # Narration / протагонист без спрайта — подбирать визуал не нужно.
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
                    if visual.outfit_asset_key:
                        result.outfit_tag = line.outfit_tag
                else:
                    logger.warning(
                        f"SceneAssetService: no visual matched for "
                        f"{character.name} outfit={line.outfit_tag} "
                        f"emotions={line.emotion_tags}"
                    )

            return result

        return await asyncio.gather(
            *(
                resolve(character, line, index)
                for index, (character, _, line) in enumerate(prepared)
            )
        )

    @staticmethod
    def current_outfits(
        characters: list[Character], assets: SceneAssets, last_outfits: dict[int, str]
    ) -> str:
        """Резолв последнего наряда каждого персонажа: character -> style-тег."""
        lines: list[str] = []

        for c in characters:
            outfit_tag = last_outfits.get(c.id)
            if not outfit_tag:
                continue
            name = next(
                (
                    entry.name
                    for entry in assets.outfits.get(c.codex_character_id, [])
                    if entry.outfit_tag == outfit_tag
                ),
                outfit_tag,
            )
            lines.append(f"- {c.name}: outfit_tag {outfit_tag} ({name})")
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
            lines.append("Backgrounds (locations and modifiers):")
            lines.append(
                f"  locations (background_changes[].location_slug): {base}"
            )
            lines.append(
                f"  modifiers (background_modifier_tags): {modifiers}"
            )
        for character in characters:
            outfits = assets.outfits.get(character.codex_character_id)
            if not outfits:
                continue
            # Codex уже отдаёт по одной группе на style-тег, объединив эмоции всех
            # спрайтов. LLM адресует наряд только тегом, поэтому каталог рендерится
            # как есть — без клиентской группировки.
            lines.append(
                f"Outfits of character {character.name} (outfit_tag → emotions):"
            )
            for entry in outfits:
                base_tags, modifier_tags = _split_emotions(entry.emotions)
                base = ", ".join(
                    f"{e.slug}={e.name}"
                    for e in sorted(base_tags, key=lambda e: e.slug)
                ) or "-"
                modifiers = ", ".join(
                    f"{e.slug}={e.name}"
                    for e in sorted(modifier_tags, key=lambda e: e.slug)
                ) or "-"
                lines.append(f"- {entry.outfit_tag} ({entry.name}):")
                lines.append(f"    base (emotion_base_tag): {base}")
                lines.append(f"    modifiers (emotion_modifier_tags): {modifiers}")
        return "\n".join(lines)

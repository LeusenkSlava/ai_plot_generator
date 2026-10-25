"""Сервис ремонта диалога: классификация дефектов и точечная починка.

Диалог — самый дорогой генератор (большой промпт + think=True + 8–16 реплик).
Перегенерация целиком из-за одного неверного имени — переплата на порядок.
Поэтому ответ классифицируется детерминированно, каждый дефект чинится самым
дешёвым способом, а полный ретрай остаётся запасным путём для неисправимых
случаев (см. ``DialogueGenerator.generate``).

Классификатор — чистые функции без LLM. Ремонт делится на две части:

* ``repair_lines`` — структурный ремонт **до** резолва ассетов: детерминированные
  фиксы (дедуп точных повторов, отбрасывание пустого ``text``, фуззи-ремап имён)
  + один батч-запрос ``think=False`` на оставшиеся дефекты (неизвестное имя,
  обрыв последней реплики).
* ``repair_tags`` — перенос существующего ремонта эмоций (обобщён на теги):
  выполняется **после** резолва ассетов, когда наряд резолвился, а эмоция — нет.
"""

import difflib
import logging
from dataclasses import dataclass, field
from enum import Enum

from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Character, DialogueLine
from src.core.novels.services.generation.assets import (
    LineAssets,
    ResolvedAssets,
    SceneAssets,
    SceneAssetService,
)
from src.core.novels.services.generation.generators.base import BaseGenerator

logger = logging.getLogger(__name__)

# Символы, которыми реплика может «правильно» заканчиваться. Если последний
# символ не из этого набора — реплика считается оборванной (TRUNCATED_END).
# Тире — валидное окончание прерванной речи («— Я не... —»).
_SENTENCE_ENDERS = frozenset('.!?…»"”)—–')


def _normalize(text: str) -> str:
    """Нормализует текст для сравнения точных повторов (схлопывает пробелы)."""
    return " ".join(text.split())


def _is_truncated(text: str) -> bool:
    """Реплика обрывается, если не заканчивается пунктуацией конца предложения."""
    stripped = text.strip()
    if not stripped:
        return False
    return stripped[-1] not in _SENTENCE_ENDERS


class DefectKind(Enum):
    NO_LINES = "no_lines"  # неисправимо → полный ретрай
    UNKNOWN_CHARACTER = "unknown_character"  # точечный LLM-фикс + фуззи-фолбэк
    EMPTY_TEXT = "empty_text"  # детерминированно (выкинуть строку)
    DUPLICATE_LINE = "duplicate_line"  # детерминированно (дедуп точных повторов)
    TRUNCATED_END = "truncated_end"  # точечный LLM-фикс (дописать финал)


@dataclass(frozen=True)
class DialogueDefect:
    kind: DefectKind
    line_index: int | None = None
    detail: str | None = None


@dataclass
class RepairResult:
    """Итог структурного ремонта: исправленные реплики + неисправимые дефекты."""

    lines_data: list[dict]
    unfixable: list[DialogueDefect] = field(default_factory=list)

    @property
    def has_unfixable(self) -> bool:
        return bool(self.unfixable)


class DialogueRepairService(BaseGenerator):
    """Классификация и точечный ремонт сгенерированного диалога."""

    def __init__(
        self,
        generator: GeneratorProtocol,
        scene_assets: SceneAssetService,
    ):
        super().__init__(generator)
        self._scene_assets = scene_assets

    # ------------------------------------------------------------------
    # Классификация (детерминированно, без LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def classify(
        lines_data: list[dict],
        valid_names: list[str],
        previous_lines: list[DialogueLine] | None = None,
    ) -> list[DialogueDefect]:
        """Детерминированно классифицирует дефекты ответа LLM.

        Возвращает список ``DialogueDefect``. Пустой ``lines_data`` даёт единственный
        дефект ``NO_LINES``. ``previous_lines`` используется как «уже виденный» текст —
        первая реплика нового диалога, дословно повторяющая реплику предыдущей сцены,
        помечается как ``DUPLICATE_LINE``.
        """
        if not lines_data:
            return [DialogueDefect(DefectKind.NO_LINES, detail="no dialogue lines")]

        valid = set(valid_names)
        seen_texts = {_normalize(line.text) for line in (previous_lines or [])}
        defects: list[DialogueDefect] = []
        last_index = len(lines_data) - 1

        for index, item in enumerate(lines_data):
            if not isinstance(item, dict):
                defects.append(
                    DialogueDefect(
                        DefectKind.UNKNOWN_CHARACTER,
                        index,
                        "line is not an object",
                    )
                )
                continue

            name = item.get("character_name")
            text = item.get("text")
            if isinstance(name, str):
                name = name.strip()

            if not isinstance(name, str) or not name or name not in valid:
                defects.append(
                    DialogueDefect(
                        DefectKind.UNKNOWN_CHARACTER,
                        index,
                        f"unknown character {name!r}",
                    )
                )

            if not isinstance(text, str) or not _normalize(text):
                defects.append(DialogueDefect(DefectKind.EMPTY_TEXT, index))
            else:
                normalized = _normalize(text)
                if normalized in seen_texts:
                    defects.append(DialogueDefect(DefectKind.DUPLICATE_LINE, index))
                else:
                    seen_texts.add(normalized)

            if index == last_index and isinstance(text, str) and _is_truncated(text):
                defects.append(DialogueDefect(DefectKind.TRUNCATED_END, index))

        return defects

    # ------------------------------------------------------------------
    # Структурный ремонт (до резолва ассетов)
    # ------------------------------------------------------------------

    async def repair_lines(
        self,
        lines_data: list[dict],
        valid_names: list[str],
        previous_lines: list[DialogueLine] | None = None,
    ) -> RepairResult:
        """Структурный ремонт реплик до резолва ассетов.

        Детерминированные фиксы (дедуп повторов, отбрасывание пустого ``text``,
        фуззи-ремап имён), затем один батч-запрос ``think=False`` на оставшиеся
        дефекты (неизвестное имя, обрыв последней реплики). Возвращает исправленный
        ``lines_data`` и список неисправимых дефектов (повод для полного ретрая).
        """
        if not lines_data:
            return RepairResult(
                [], [DialogueDefect(DefectKind.NO_LINES, detail="no dialogue lines")]
            )

        repaired = list(lines_data)

        # 1. Детерминированные фиксы.
        repaired = self._drop_empty_and_duplicates(repaired, previous_lines)
        if not repaired:
            return RepairResult(
                [],
                [
                    DialogueDefect(
                        DefectKind.NO_LINES, detail="all lines empty or duplicate"
                    )
                ],
            )
        repaired = self._fuzzy_remap_names(repaired, valid_names)

        # 2. Оставшиеся дефекты, требующие LLM, — одним батч-запросом.
        defects = self.classify(repaired, valid_names, previous_lines)
        needs_llm = [
            d
            for d in defects
            if d.kind in (DefectKind.UNKNOWN_CHARACTER, DefectKind.TRUNCATED_END)
        ]
        if needs_llm:
            repaired = await self._llm_fix_lines(repaired, valid_names, needs_llm)

        # 3. Перевалидация: неисправимые дефекты — повод для полного ретрая.
        defects = self.classify(repaired, valid_names, previous_lines)
        unfixable = [
            d
            for d in defects
            if d.kind
            in (
                DefectKind.NO_LINES,
                DefectKind.UNKNOWN_CHARACTER,
                DefectKind.TRUNCATED_END,
            )
        ]
        return RepairResult(repaired, unfixable)

    def _drop_empty_and_duplicates(
        self,
        lines_data: list[dict],
        previous_lines: list[DialogueLine] | None,
    ) -> list[dict]:
        """Отбрасывает пустые реплики и точные повторы (в т.ч. из прошлой сцены)."""
        seen: set[str] = {_normalize(line.text) for line in (previous_lines or [])}
        kept: list[dict] = []
        for item in lines_data:
            if not isinstance(item, dict):
                kept.append(item)  # битый элемент оставляем — UNKNOWN_CHARACTER
                continue
            text = item.get("text")
            normalized = _normalize(text) if isinstance(text, str) else ""
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            kept.append(item)
        return kept

    def _fuzzy_remap_names(
        self, lines_data: list[dict], valid_names: list[str]
    ) -> list[dict]:
        """Детерминированный фуззи-ремап неизвестных имён (без LLM)."""
        for item in lines_data:
            if not isinstance(item, dict):
                continue
            name = item.get("character_name")
            if isinstance(name, str):
                name = name.strip()
                item["character_name"] = name
            if isinstance(name, str) and name in valid_names:
                continue
            remapped = (
                self._fuzzy_name(name, valid_names) if isinstance(name, str) else None
            )
            if remapped is not None:
                item["character_name"] = remapped
        return lines_data

    @staticmethod
    def _fuzzy_name(name: str, valid_names: list[str]) -> str | None:
        """Возвращает каноническое имя по точному (без регистра) или фуззи-совпадению."""
        folded = name.casefold()
        for valid in valid_names:
            if valid.casefold() == folded:
                return valid
        matches = difflib.get_close_matches(name, valid_names, n=1, cutoff=0.8)
        return matches[0] if matches else None

    async def _llm_fix_lines(
        self,
        lines_data: list[dict],
        valid_names: list[str],
        defects: list[DialogueDefect],
    ) -> list[dict]:
        """Один батч-запрос ``think=False`` на неизвестные имена и оборванные финалы."""
        by_index = {d.line_index: d for d in defects if d.line_index is not None}
        items_to_fix: list[tuple[int, dict, DialogueDefect]] = []
        for index in sorted(by_index):
            item = lines_data[index]
            if not isinstance(item, dict):
                continue
            items_to_fix.append((index, item, by_index[index]))

        if not items_to_fix:
            return lines_data

        data = await self._generate(
            self._line_repair_prompt(items_to_fix, valid_names), think=False
        )
        fixes = self._index_by_field(data.get("fixes") or [], "index")

        for position, (index, item, _defect) in enumerate(items_to_fix, start=1):
            fix = fixes.get(position)
            if not isinstance(fix, dict):
                continue
            name = fix.get("character_name")
            if isinstance(name, str) and name in valid_names:
                item["character_name"] = name
            text = fix.get("text")
            if isinstance(text, str) and text.strip():
                item["text"] = text

        return lines_data

    def _line_repair_prompt(
        self,
        items_to_fix: list[tuple[int, dict, DialogueDefect]],
        valid_names: list[str],
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "You fix defects in the generated dialogue lines of a visual novel. "
                "The dialogue is otherwise final: correct ONLY the listed lines and "
                "do not change the others. Choose character_name strictly from the "
                "scene participants list. If a line is cut off mid-sentence, complete "
                "its text so it ends at a natural stopping point.\n"
                "For each line return:\n"
                "1. index - the line's number as given;\n"
                "2. character_name - the corrected speaker name;\n"
                "3. text - the corrected text.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                '{"fixes": [{"index": integer, "character_name": string, "text": string}]}'
            ),
        }
        participants = ", ".join(valid_names)
        line_items = [
            f"{position}. [defect: {defect.kind.value}] "
            f"{item.get('character_name', '?')}: \"{item.get('text', '')}\""
            for position, (_, item, defect) in enumerate(items_to_fix, start=1)
        ]
        user_content = (
            f"Scene participants (use ONLY these names): {participants}\n\n"
            "Lines to fix:\n" + "\n".join(line_items)
        )
        return [system_prompt, {"role": "user", "content": user_content}]

    @staticmethod
    def _index_by_field(items: object, field: str) -> dict[int, dict]:
        """Сводит ответ LLM к ``{index: {...}}``; некорректные записи отбрасываются."""
        by_index: dict[int, dict] = {}
        if not isinstance(items, list):
            return by_index
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get(field))
            except (TypeError, ValueError):
                continue
            by_index[index] = item
        return by_index

    # ------------------------------------------------------------------
    # Ремонт тегов (после резолва ассетов) — перенос _fix_missing_emotions
    # ------------------------------------------------------------------

    async def repair_tags(
        self,
        prepared: list[tuple[Character, dict, LineAssets]],
        resolved: list[ResolvedAssets],
        assets: SceneAssets,
        universe_id: int | None,
    ) -> list[ResolvedAssets]:
        """Перевыбирает эмоции реплик, где наряд резолвился, а эмоция — нет.

        Причина — emotion_base_tag, которого нет в каталоге выбранного наряда
        (LLM выдумал slug). Текст при этом корректен, поэтому перегенерация всей
        сцены не нужна: одним коротким запросом просим LLM выбрать эмоцию заново
        строго из каталога и до-резолвим только emotion_asset_key.
        """
        if universe_id is None:
            return resolved

        missing: list[tuple[int, Character, str, str]] = []
        for index, (character, item, line) in enumerate(prepared):
            if character.is_protagonist:
                continue
            picked = resolved[index]
            if picked.outfit_asset_key is None or picked.emotion_asset_key is not None:
                continue
            outfit_tag = line.outfit_tag
            if not outfit_tag:
                continue
            missing.append((index, character, outfit_tag, item["text"]))

        if not missing:
            return resolved

        data = await self._generate(
            self._emotion_repair_prompt(missing, assets), think=False
        )
        response_by_index = self._index_by_field(data.get("lines") or [], "index")

        for position, (index, character, outfit_tag, _) in enumerate(missing, start=1):
            base_slugs, modifier_slugs = self._scene_assets.emotions_for_outfit(
                assets, character.codex_character_id, outfit_tag
            )
            base_tag, modifier_tags = self._pick_tag(
                response_by_index.get(position), base_slugs, modifier_slugs
            )
            if base_tag is None:
                continue
            emotion_asset_key = await self._scene_assets.match_emotion_asset(
                character.codex_character_id, outfit_tag, [base_tag, *modifier_tags]
            )
            if emotion_asset_key:
                resolved[index].emotion_asset_key = emotion_asset_key

        return resolved

    def _emotion_repair_prompt(
        self,
        missing: list[tuple[int, Character, str, str]],
        assets: SceneAssets,
    ) -> list[dict]:
        system_prompt = {
            "role": "system",
            "content": (
                "You fix the emotion tags of the generated dialogue lines below. "
                "The text of each line is final and must stay unchanged; you only choose "
                "the emotion shown on the speaker's sprite. Pick the emotion that best "
                "matches the mood of each line, using ONLY the slugs listed for that "
                "character's outfit in the catalog. Do not invent slugs and do not reuse "
                "emotions of other characters or outfits.\n"
                "For each line return:\n"
                "1. index - the line's number as given;\n"
                "2. emotion_base_tag - ONE base emotion slug from the catalog for that outfit;\n"
                "3. emotion_modifier_tags - 0 or more modifier slugs from the catalog for that "
                "outfit.\n"
                "Answer STRICTLY as JSON matching this schema:\n"
                """
                {
                  "lines": [
                    {"index": integer, "emotion_base_tag": string, "emotion_modifier_tags": [string]}
                  ]
                }
                """
            ),
        }

        catalog_lines: list[str] = []
        seen: set[tuple[int | None, str]] = set()
        for _, character, outfit_tag, _ in missing:
            key = (character.codex_character_id, outfit_tag)
            if key in seen:
                continue
            seen.add(key)
            base_slugs, modifier_slugs = self._scene_assets.emotions_for_outfit(
                assets, character.codex_character_id, outfit_tag
            )
            base = ", ".join(base_slugs) or "-"
            modifiers = ", ".join(modifier_slugs) or "-"
            catalog_lines.append(
                f"- {character.name} (outfit_tag {outfit_tag}): "
                f"base: {base}; modifiers: {modifiers}"
            )

        line_items = [
            f'{position}. {character.name} (outfit_tag {outfit_tag}): "{text}"'
            for position, (_, character, outfit_tag, text) in enumerate(
                missing, start=1
            )
        ]

        user_content = (
            "Catalog (character -> outfit_tag -> emotions):\n"
            + "\n".join(catalog_lines)
            + "\n\nLines to fix:\n"
            + "\n".join(line_items)
        )
        return [system_prompt, {"role": "user", "content": user_content}]

    @staticmethod
    def _pick_tag(
        item: dict | None,
        base_slugs: list[str],
        modifier_slugs: list[str],
        base_field: str = "emotion_base_tag",
        modifier_field: str = "emotion_modifier_tags",
    ) -> tuple[str | None, list[str]]:
        """Проверяет выбранные LLM теги; при невалидности — детерминированный запасной.

        Фолбэк: ``normal`` → первый base-slug (тот же, что был для эмоций; поле
        параметризуется, чтобы переиспользовать для фона).
        """
        base_tag: str | None = None
        modifier_tags: list[str] = []
        if isinstance(item, dict):
            base_tag = item.get(base_field)
            raw = item.get(modifier_field) or []
            if isinstance(raw, list):
                modifier_tags = [str(m) for m in raw]
        if base_tag not in base_slugs or not all(
            m in modifier_slugs for m in modifier_tags
        ):
            base_tag = (
                "normal"
                if "normal" in base_slugs
                else (base_slugs[0] if base_slugs else None)
            )
            modifier_tags = []
        return base_tag, modifier_tags

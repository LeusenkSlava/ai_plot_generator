from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from src.core._shared.models.llm_base import LLMGeneratedModel


class NovelMode(StrEnum):
    """Режим интерактивности новеллы."""

    LINEAR = "linear"
    INTERACTIVE = "interactive"


class LineKind(StrEnum):
    """Тип реплики диалога"""

    SPEECH = "speech"
    THOUGHT = "thought"
    NARRATION = "narration"


class PromptVariant(StrEnum):
    """Набор шаблонов промптов, используемых при генерации новеллы."""

    DEFAULT = "default"
    NSFW_LOW = "nsfw_low"
    NSFW_MEDIUM = "nsfw_medium"
    NSFW_HIGH = "nsfw_high"


DEFAULT_PROMPT_VARIANT = PromptVariant.DEFAULT


class PromptKey(StrEnum):
    """Канонические ключи шаблонов промптов"""

    NOVEL = "novel"
    CHARACTER = "character"
    ROADMAP = "roadmap"
    SCENE = "scene"
    DIALOGUE = "dialogue"
    STORY_CONTEXT = "story_context"
    BRANCH_ROADMAP = "branch_roadmap"
    SCENE_VALIDATOR = "scene_validator"


@dataclass
class Character:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    novel_id: int
    name: str
    role: str
    arc: str
    voice_notes: str
    # id персонажа в Codex; только для новелл с universe_id
    codex_character_id: int | None = None

    gender: str | None = None

    is_protagonist: bool = False


@dataclass
class Roadmap:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    novel_id: int
    # Глубина по пути от корня (1..N). Не глобальный номер: у разных веток
    # значения повторяются, адресом шага служит только суррогатный id.
    depth: int
    title: str
    event: str
    conflict: str
    change: str
    target_choice: bool
    choice_stakes: str | None
    scenes_count: int
    # место и время действия шага. Задаются RoadmapGenerator из каталога локаций
    # Codex и делают оси location/time у валидатора сцен осмысленными.
    location_slug: str | None = None
    time_of_day: str | None = None
    day: int | None = None
    # Ребро дерева: шаг, из которого пришли (None только у корня).
    parent_roadmap_id: int | None = None
    # Номер ветки; 0 = истинная ветка.
    branch_id: int = 0


@dataclass
class Scene:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    roadmap_id: int
    title: str
    description: str
    order: int
    # последняя сцена шага роадмапа / последняя сцена всей новеллы
    is_final_for_roadmap: bool = False
    is_final_for_novel: bool = False
    # изложение истории после этой сцены: сюжетные факты и внешность/одежда персонажей.
    # Передаётся в генерацию следующей сцены и пересобирается после неё
    story_context: str | None = None
    # явный список «кто в сцене» (id персонажей); формируется SceneGenerator по месту/времени
    # шага и передаётся в DialogueGenerator вместо всего каста
    character_ids: list[int] = field(default_factory=list)
    # место и время действия сцены; наследуются от шага роадмапа, если LLM их не вернул.
    # Нужны валидатору (сверка с шагом) и как якорь непрерывности для следующей сцены.
    location_slug: str | None = None
    time_of_day: str | None = None
    day: int | None = None
    # сцена не прошла смысловую проверку соответствия шагу роадмапа даже после
    # ретраев — требует ручного вмешательства
    needs_review: bool = False
    review_reason: str | None = None


@dataclass
class Novel(LLMGeneratedModel):
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    title: str
    public_description: str
    description: str
    tone: str
    universe_id: int | None = None
    mode: NovelMode = NovelMode.LINEAR

    prompt_variant: PromptVariant = DEFAULT_PROMPT_VARIANT

    _LLM_FIELDS: ClassVar[dict[str, str]] = {
        "title": "short, catchy title",
        "public_description": "user-facing description, NO spoilers",
        "description": "main description of the story; the plot will be generated from it",
        "tone": "tone and narrative style",
    }

    @classmethod
    def from_llm(
        cls,
        data: dict,
        *,
        universe_id: int | None = None,
        mode: NovelMode = NovelMode.LINEAR,
        prompt_variant: PromptVariant = DEFAULT_PROMPT_VARIANT,
    ) -> "Novel":
        return cls(
            id=None,
            created_at=None,
            updated_at=None,
            universe_id=universe_id,
            mode=mode,
            prompt_variant=prompt_variant,
            **cls.llm_values(data),
        )


@dataclass
class DialogueLine:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    novel_id: int
    scene_id: int
    # NULL только для kind="narration" (описание без говорящего).
    character_id: int | None

    order: int
    text: str
    # последняя реплика сцены
    is_final_for_scene: bool
    # Тип реплики: речь вслух / внутренние мысли протагониста / описание-ремарка.
    kind: LineKind = LineKind.SPEECH

    # asset_key ассетов Codex; заполняются только для новелл с universe_id
    background_asset_key: str | None = None
    sound_asset_key: str | None = None
    sprite_asset_key: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


@dataclass
class RoadmapChoice:
    """Вариант выбора на шаге роадмапа (target_choice)."""

    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    roadmap_id: int

    order: int
    text: str
    # Продолжение истинной ветки; ведёт на уже существующий следующий шаг спайна.
    is_true: bool = False
    # Завязка альтернативной ветки (для ленивой генерации после выбора).
    branch_direction: str | None = None
    # Куда ведёт выбор: для is_true — следующий шаг спайна, для форка — NULL до
    # момента выбора, после генерации ветки — её первый шаг.
    next_roadmap_id: int | None = None


@dataclass
class PlayerChoice:
    """Запись о выбранном игроком варианте (журнал пути)."""

    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    novel_id: int
    roadmap_choice_id: int
    # Реплика, на которой был показан выбор (для трассировки).
    dialogue_line_id: int | None = None


@dataclass
class Prompt:
    """Версия шаблона промпта.

    Шаблоны хранятся в БД (таблица ``prompts``) и версионируются append-only:
    правка добавляет новую версию (``version`` + 1) и деактивирует предыдущую.
    ``system_template`` и ``user_template`` — тексты с плейсхолдерами вида
    ``{var}``; рендерит их :class:`PromptCatalog`.
    """

    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    key: str
    variant: str
    version: int
    system_template: str
    user_template: str
    is_active: bool = True

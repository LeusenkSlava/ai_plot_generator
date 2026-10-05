import json
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from src.core._shared.models.llm_base import LLMGeneratedModel


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


@dataclass
class Roadmap:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    novel_id: int
    step_id: int
    title: str
    goal: str
    target_choice: bool
    choice_stakes: str | None
    scenes_count: int


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

    _LLM_FIELDS: ClassVar[dict[str, str]] = {
        "title": "короткое, цепляющее название",
        "public_description": "описание для пользователя, БЕЗ спойлеров",
        "description": "главное описание истории, по нему будет генерироваться сюжет",
        "tone": "тон и стиль повествования",
    }

    @classmethod
    def from_llm(cls, data: dict, *, universe_id: int | None = None) -> "Novel":
        return cls(
            id=None,
            created_at=None,
            updated_at=None,
            universe_id=universe_id,
            **cls.llm_values(data),
        )


@dataclass
class DialogueLine:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    novel_id: int
    scene_id: int
    character_id: int

    order: int
    text: str
    # последняя реплика сцены
    is_final_for_scene: bool

    # asset_key ассетов Codex; заполняются только для новелл с universe_id
    background_asset_key: str | None = None
    sprite_asset_key: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


@dataclass
class DialogueAction:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    dialogue_line_id: int

    order: int
    text: str
    next_roadmap_id: int | None

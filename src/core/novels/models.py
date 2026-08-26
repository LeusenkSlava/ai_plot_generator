from dataclasses import dataclass
from datetime import datetime


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

@dataclass
class Scene:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    roadmap_id: int
    title: str
    description: str
    order: int

@dataclass
class Novel:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    title: str
    public_description: str
    description: str
    tone: str

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
    is_final_for_roadmap: bool

@dataclass
class DialogueAction:
    id: int | None
    created_at: datetime | None
    updated_at: datetime | None

    dialogue_line_id: int

    order: int
    text: str
    next_roadmap_id: int | None

from dataclasses import dataclass, field
from enum import StrEnum


class TagType(StrEnum):
    EMOTION = "emotion"
    OUTFIT_STYLE = "outfit_style"
    LOCATION = "location"
    TIME_OF_DAY = "time_of_day"
    ARCHETYPE = "archetype"


class TagKind(StrEnum):
    BASE = "base"
    MODIFIER = "modifier"


@dataclass
class Tag:
    id: int
    type: TagType
    slug: str
    name: str
    kind: TagKind | None = None


@dataclass
class Universe:
    id: int
    slug: str
    title: str
    description: str


@dataclass
class CodexCharacter:
    id: int
    universe_id: int
    slug: str
    name: str
    description: str
    speech_style: dict | None = None
    tags: list[Tag] = field(default_factory=list)


@dataclass
class Background:
    id: int
    universe_id: int
    slug: str
    description: str
    asset_key: str
    tags: list[Tag] = field(default_factory=list)


@dataclass
class Sprite:
    id: int
    character_id: int
    slug: str
    description: str
    asset_key: str
    tags: list[Tag] = field(default_factory=list)


@dataclass
class Emotion:
    id: int
    sprite_id: int
    slug: str
    name: str
    asset_key: str
    tags: list[Tag] = field(default_factory=list)


@dataclass
class Outfit:
    id: int
    sprite_id: int
    slug: str
    name: str
    asset_key: str
    tags: list[Tag] = field(default_factory=list)


@dataclass
class EmotionTags:
    """Доступные персонажу emotion-теги, разделённые по роли."""

    base: list[Tag] = field(default_factory=list)
    modifiers: list[Tag] = field(default_factory=list)


@dataclass
class EmotionMatchItem:
    """Запрос подбора эмоции для одного персонажа."""

    character_id: int
    tags: list[str]
    sprite_id: int | None = None

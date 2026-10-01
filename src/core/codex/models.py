from dataclasses import dataclass, field
from enum import StrEnum


class TagType(StrEnum):
    EMOTION = "emotion"
    OUTFIT_STYLE = "outfit_style"
    LOCATION = "location"
    TIME_OF_DAY = "time_of_day"
    ARCHETYPE = "archetype"


@dataclass
class Tag:
    id: int
    type: TagType
    slug: str
    name: str


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

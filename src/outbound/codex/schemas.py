from pydantic import BaseModel

from src.core.codex.models import TagType


class TagSchema(BaseModel):
    id: int
    type: TagType
    slug: str
    name: str


class UniverseSchema(BaseModel):
    id: int
    slug: str
    title: str
    description: str


class CharacterSchema(BaseModel):
    id: int
    universe_id: int
    slug: str
    name: str
    description: str
    speech_style: dict | None = None
    tags: list[TagSchema] = []


class BackgroundSchema(BaseModel):
    id: int
    universe_id: int
    slug: str
    description: str
    asset_key: str
    tags: list[TagSchema] = []


class SpriteSchema(BaseModel):
    id: int
    character_id: int
    slug: str
    description: str
    asset_key: str
    tags: list[TagSchema] = []


class EmotionSchema(BaseModel):
    id: int
    sprite_id: int
    slug: str
    name: str
    asset_key: str
    tags: list[TagSchema] = []


class OutfitSchema(BaseModel):
    id: int
    sprite_id: int
    slug: str
    name: str
    asset_key: str
    tags: list[TagSchema] = []

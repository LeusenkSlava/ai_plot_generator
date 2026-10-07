from pydantic import BaseModel

from src.core.codex.models import TagKind, TagType


class TagSchema(BaseModel):
    id: int
    type: TagType
    slug: str
    name: str
    kind: TagKind | None = None


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


class EmotionTagsRequest(BaseModel):
    """Тело запроса подбора одной эмоции."""

    sprite_id: int | None = None
    tags: list[str]


class EmotionMatchItemSchema(BaseModel):
    """Элемент батча подбора эмоций."""

    character_id: int
    sprite_id: int | None = None
    tags: list[str]


class EmotionTagsResponse(BaseModel):
    """Доступные персонажу emotion-теги, разделённые по роли."""

    base: list[TagSchema] = []
    modifiers: list[TagSchema] = []


class OutfitMatchRequest(BaseModel):
    """Тело запроса подбора одной одежды по тегу."""

    tag: str

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
    gender: str | None = None
    tags: list[TagSchema] = []


class BackgroundSchema(BaseModel):
    id: int
    universe_id: int
    slug: str
    description: str
    asset_key: str
    sound_asset_key: str | None = None
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


class OutfitCatalogSchema(OutfitSchema):
    emotions: list[EmotionSchema] = []


class VisualMatchRequest(BaseModel):
    outfit_tag: str
    emotion_tags: list[str] = []


class VisualMatchResponse(BaseModel):
    sprite_asset_key: str | None = None
    outfit_asset_key: str | None = None
    emotion_asset_key: str | None = None


class BackgroundTagsResponse(BaseModel):
    """Доступные вселенной теги задников, разделённые по роли (kind)."""

    base: list[TagSchema] = []
    modifiers: list[TagSchema] = []


class BackgroundTagsRequest(BaseModel):
    """Тело запроса подбора одного задника по тегам-смыслам."""

    tags: list[str]


class BackgroundMatchItemSchema(BaseModel):
    """Элемент батча подбора задников: вселенная + набор тегов-смыслов."""

    universe_id: int
    tags: list[str]

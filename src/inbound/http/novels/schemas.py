from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class NovelCreateRequest(BaseModel):
    prompt: str
    universe_id: int | None = None

class NovelResponse(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    title: str
    public_description: str
    description: str
    tone: str
    universe_id: int | None


class NovelListResponse(BaseModel):
    items: list[NovelResponse]
    total: int
    limit: int
    offset: int


class CharacterResponse(BaseModel):
    id: int
    name: str
    role: str


class DialogueLineResponse(BaseModel):
    id: int
    scene_id: int
    order: int
    text: str
    is_final_for_scene: bool
    background_asset_key: str | None
    sprite_asset_key: str | None
    outfit_asset_key: str | None
    emotion_asset_key: str | None


class SceneResponse(BaseModel):
    id: int
    roadmap_id: int
    title: str
    order: int
    is_final_for_roadmap: bool
    is_final_for_novel: bool


class DialogueStepResponse(BaseModel):
    dialogue: DialogueLineResponse
    scene: SceneResponse
    character: CharacterResponse


class PlaybackOkResponse(BaseModel):
    """Следующая реплика есть."""

    status: Literal["ok"]
    step: DialogueStepResponse


class PlaybackPendingResponse(BaseModel):
    """Реплики кончились, роадмап не пройден.

    need_generation — нужно отправить команду в ai_plot.scene.generate;
    generating — сцена уже генерируется.
    """

    status: Literal["need_generation", "generating"]
    next_scene_order: int


class PlaybackFinishedResponse(BaseModel):
    """Новелла пройдена до конца."""

    status: Literal["finished"]


PlaybackResponse = Annotated[
    PlaybackOkResponse | PlaybackPendingResponse | PlaybackFinishedResponse,
    Field(discriminator="status"),
]

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from src.core.novels.models import NovelMode


class NovelCreateRequest(BaseModel):
    prompt: str
    universe_id: int | None = None
    mode: NovelMode = NovelMode.LINEAR

class NovelResponse(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    title: str
    public_description: str
    description: str
    tone: str
    universe_id: int | None
    mode: NovelMode


class NovelListResponse(BaseModel):
    items: list[NovelResponse]
    total: int
    limit: int
    offset: int


class CharacterResponse(BaseModel):
    id: int
    name: str
    role: str
    is_protagonist: bool


class DialogueLineResponse(BaseModel):
    id: int
    scene_id: int
    order: int
    text: str
    is_final_for_scene: bool
    is_thought: bool
    background_asset_key: str | None
    sound_asset_key: str | None
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
    location_slug: str | None = None
    time_of_day: str | None = None
    day: int | None = None


class DialogueStepResponse(BaseModel):
    dialogue: DialogueLineResponse
    scene: SceneResponse
    character: CharacterResponse


class RoadmapChoiceResponse(BaseModel):
    id: int
    text: str
    is_true: bool


class PlaybackOkResponse(BaseModel):
    """Следующая реплика есть."""

    status: Literal["ok"]
    step: DialogueStepResponse


class PlaybackChoiceResponse(BaseModel):
    """Текущая реплика — точка выбора; в ``choices`` лежат варианты."""

    status: Literal["choice"]
    step: DialogueStepResponse
    choices: list[RoadmapChoiceResponse]


class PlaybackPendingResponse(BaseModel):
    """Реплики кончились, роадмап не пройден.

    need_generation — нужно отправить команду в ai_plot.scene.generate с
    roadmap_id и position; generating — сцена уже генерируется.
    """

    status: Literal["need_generation", "generating"]
    next_roadmap_id: int
    next_position: int


class PlaybackFinishedResponse(BaseModel):
    """Новелла пройдена до конца."""

    status: Literal["finished"]


PlaybackResponse = Annotated[
    PlaybackOkResponse
    | PlaybackChoiceResponse
    | PlaybackPendingResponse
    | PlaybackFinishedResponse,
    Field(discriminator="status"),
]


class ChooseRequest(BaseModel):
    roadmap_choice_id: int
    dialogue_line_id: int | None = None


class ChooseResponse(BaseModel):
    status: Literal["ok", "need_branch_generation"]

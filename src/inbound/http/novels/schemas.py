from datetime import datetime

from pydantic import BaseModel


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

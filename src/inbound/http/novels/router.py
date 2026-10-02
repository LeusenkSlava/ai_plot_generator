import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.novels.exceptions import (
    DialogueLineNotFoundError,
    NovelNotFoundError,
)
from src.core.novels.services.crud import NovelService
from src.core.novels.services.playback import NovelPlaybackService
from src.inbound.http.novels.dependencies import (
    get_novel_playback_service,
    get_novel_service,
)
from src.inbound.http.novels.schemas import (
    NovelListResponse,
    NovelResponse,
    PlaybackResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/novels", tags=["novels"])


@router.get("/{novel_id}", response_model=NovelResponse)
async def get_novel(
    novel_id: int,
    service: Annotated[NovelService, Depends(get_novel_service)],
):
    novel = await service.get(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


@router.get(
    "/start/{novel_id}",
    response_model=PlaybackResponse,
    responses={404: {"description": "Novel or dialogue line (offset) not found"}},
)
async def start_novel(
    novel_id: int,
    service: Annotated[NovelPlaybackService, Depends(get_novel_playback_service)],
    offset: int | None = None,
):
    """offset — id последней показанной реплики; без него новелла начинается с начала.

    Только читает из БД, LLM не вызывает. status:
    - ok — следующая реплика в step;
    - need_generation — реплики кончились, нужно отправить в Kafka-топик ai_plot.scene.generate
      команду на генерацию сцены next_scene_order;
    - generating — сцена next_scene_order уже генерируется;
    - finished — новелла пройдена до конца.
    """
    try:
        result = await service.next(novel_id, offset)
    except NovelNotFoundError:
        raise HTTPException(status_code=404, detail="Novel not found")
    except DialogueLineNotFoundError:
        raise HTTPException(status_code=404, detail="Dialogue line not found")
    if result.status == "ok":
        return {"status": "ok", "step": result.step}
    if result.status == "finished":
        return {"status": "finished"}
    return {"status": result.status, "next_scene_order": result.next_scene_order}


@router.get("/", response_model=NovelListResponse)
async def list_novels(
    service: Annotated[NovelService, Depends(get_novel_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    novels, total = await service.list(limit=limit, offset=offset)
    return {"items": novels, "total": total, "limit": limit, "offset": offset}


@router.delete("/{novel_id}", status_code=204)
async def delete_novel(
    novel_id: int,
    service: Annotated[NovelService, Depends(get_novel_service)],
):
    await service.delete(novel_id)

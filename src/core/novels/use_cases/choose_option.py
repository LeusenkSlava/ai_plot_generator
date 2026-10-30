from enum import StrEnum

from src.core.novels.exceptions import (
    NovelNotFoundError,
    RoadmapChoiceNotFoundError,
)
from src.core.novels.interfaces.repository import NovelRepositoryProtocol
from src.core.novels.models import PlayerChoice
from src.core.novels.services.crud import (
    PlayerChoiceService,
    RoadmapChoiceService,
    RoadmapService,
)
from src.core.novels.services.generation.transactions import TransactionFactory


class ChooseOutcome(StrEnum):
    OK = "ok"
    NEED_BRANCH_GENERATION = "need_branch_generation"


class ChooseOptionUseCase:
    """Зафиксировать выбор игрока на развилке.

    Записывает вариант в журнал ``player_choices`` (идемпотентно) и сообщает, нужно
    ли лениво генерировать альтернативную ветку (у форка next_roadmap_id ещё NULL).
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_service: RoadmapService,
        choice_service: RoadmapChoiceService,
        player_choice_service: PlayerChoiceService,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_service
        self._choices = choice_service
        self._player_choices = player_choice_service

    async def execute(
        self,
        novel_id: int,
        roadmap_choice_id: int,
        dialogue_line_id: int | None = None,
        *,
        step: TransactionFactory,
    ) -> ChooseOutcome:
        async with step():
            if await self._novels.get_by_id(novel_id) is None:
                raise NovelNotFoundError(novel_id)

            choice = await self._choices.get(roadmap_choice_id)
            if choice is None:
                raise RoadmapChoiceNotFoundError(roadmap_choice_id)

            roadmap = await self._roadmaps.get(choice.roadmap_id)
            if roadmap is None or roadmap.novel_id != novel_id:
                raise RoadmapChoiceNotFoundError(roadmap_choice_id)

            existing = await self._player_choices.get_by_roadmap_choice(
                roadmap_choice_id
            )
            if existing is None:
                await self._player_choices.add(
                    PlayerChoice(
                        id=None,
                        created_at=None,
                        updated_at=None,
                        novel_id=novel_id,
                        roadmap_choice_id=roadmap_choice_id,
                        dialogue_line_id=dialogue_line_id,
                    )
                )

        if choice.next_roadmap_id is not None:
            return ChooseOutcome.OK
        return ChooseOutcome.NEED_BRANCH_GENERATION

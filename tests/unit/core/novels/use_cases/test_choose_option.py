"""Повторный выбор на развилке заменяет прежний.

Регрессия: ``player_choices`` пополнялся по одному разу на каждый вариант, поэтому
после перепрохождения и выбора ранее выбранного варианта новый выбор не попадал в
журнал, и путь оставался на другой ветке.
"""

from src.core.novels.models import PlayerChoice, RoadmapChoice
from src.core.novels.services.crud import (
    PlayerChoiceService,
    RoadmapChoiceService,
    RoadmapService,
)
from src.core.novels.services.generation.transactions import noop_step
from src.core.novels.use_cases.choose_option import (
    ChooseOptionUseCase,
    ChooseOutcome,
)
from tests.factories import novel_domain, roadmap_domain
from tests.fakes.outbound.database.repositories.novel_repository import (
    FakeNovelRepository,
)
from tests.fakes.outbound.database.repositories.player_choice_repository import (
    FakePlayerChoiceRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_choice_repository import (
    FakeRoadmapChoiceRepository,
)
from tests.fakes.outbound.database.repositories.roadmap_repository import (
    FakeRoadmapRepository,
)


def _choice(
    roadmap_id: int,
    *,
    order: int,
    text: str,
    is_true: bool,
    next_roadmap_id: int | None,
) -> RoadmapChoice:
    return RoadmapChoice(
        id=None,
        created_at=None,
        updated_at=None,
        roadmap_id=roadmap_id,
        order=order,
        text=text,
        is_true=is_true,
        next_roadmap_id=next_roadmap_id,
    )


async def _setup():
    novels = FakeNovelRepository()
    novel = await novels.add(novel_domain(is_published=True))

    roadmaps = FakeRoadmapRepository()
    fork = await roadmaps.add(roadmap_domain(target_choice=True))

    choices = FakeRoadmapChoiceRepository()
    true_choice = await choices.add(
        _choice(fork.id, order=1, text="Истинный", is_true=True, next_roadmap_id=99)
    )
    alt_choice = await choices.add(
        _choice(
            fork.id,
            order=2,
            text="Альтернативный",
            is_true=False,
            next_roadmap_id=None,
        )
    )

    player_choices = FakePlayerChoiceRepository()
    use_case = ChooseOptionUseCase(
        novel_repository=novels,
        roadmap_service=RoadmapService(roadmaps),
        choice_service=RoadmapChoiceService(choices),
        player_choice_service=PlayerChoiceService(player_choices),
    )
    return novel, use_case, player_choices, true_choice, alt_choice


async def _chosen_ids(player_choices, novel_id: int) -> list[int]:
    return [
        pc.roadmap_choice_id
        for pc in await player_choices.list_by_novel_id(novel_id)
    ]


class TestChooseOptionReplay:
    async def test_choose_records_choice(self):
        novel, use_case, player_choices, true_choice, _ = await _setup()

        outcome = await use_case.execute(
            novel.id, true_choice.id, step=noop_step
        )

        assert outcome == ChooseOutcome.OK
        assert await _chosen_ids(player_choices, novel.id) == [true_choice.id]

    async def test_new_choice_on_same_fork_replaces_previous(self):
        """Выбор альтернативы убирает прежний выбор истинной ветки."""
        novel, use_case, player_choices, true_choice, alt_choice = await _setup()
        await use_case.execute(novel.id, true_choice.id, step=noop_step)

        outcome = await use_case.execute(
            novel.id, alt_choice.id, step=noop_step
        )

        assert outcome == ChooseOutcome.NEED_BRANCH_GENERATION
        assert await _chosen_ids(player_choices, novel.id) == [alt_choice.id]

    async def test_reselecting_previous_choice_switches_path_back(self):
        """Повторный выбор ранее выбранного варианта снова меняет путь."""
        novel, use_case, player_choices, true_choice, alt_choice = await _setup()
        await use_case.execute(novel.id, true_choice.id, step=noop_step)
        await use_case.execute(novel.id, alt_choice.id, step=noop_step)

        outcome = await use_case.execute(
            novel.id, true_choice.id, step=noop_step
        )

        assert outcome == ChooseOutcome.OK
        assert await _chosen_ids(player_choices, novel.id) == [true_choice.id]

    async def test_repeat_of_the_same_choice_is_idempotent(self):
        """Повтор POST того же варианта не создаёт дубль записи."""
        novel, use_case, player_choices, true_choice, _ = await _setup()

        await use_case.execute(novel.id, true_choice.id, step=noop_step)
        await use_case.execute(novel.id, true_choice.id, step=noop_step)

        assert await _chosen_ids(player_choices, novel.id) == [true_choice.id]

    async def test_legacy_two_choices_for_fork_are_collapsed_to_selected(self):
        """Старые записи обоих вариантов (до фикса) не перебивают новый выбор."""
        novel, use_case, player_choices, true_choice, alt_choice = await _setup()
        await player_choices.add(
            PlayerChoice(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                roadmap_choice_id=true_choice.id,
            )
        )
        await player_choices.add(
            PlayerChoice(
                id=None,
                created_at=None,
                updated_at=None,
                novel_id=novel.id,
                roadmap_choice_id=alt_choice.id,
            )
        )

        await use_case.execute(novel.id, true_choice.id, step=noop_step)

        assert await _chosen_ids(player_choices, novel.id) == [true_choice.id]

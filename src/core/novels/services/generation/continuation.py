import logging
from dataclasses import dataclass

from src.core.novels.exceptions import (
    NovelFinishedError,
    NovelNotFoundError,
    SceneOrderError,
)
from src.core.novels.interfaces.repository import (
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    PlayerChoiceRepositoryProtocol,
    RoadmapChoiceRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.llm_trace import llm_trace
from src.core.novels.models import Scene
from src.core.novels.services.generation.generators.dialogue import DialogueGenerator
from src.core.novels.services.generation.generators.scene import SceneGenerator
from src.core.novels.services.generation.generators.story_context import (
    StoryContextGenerator,
    render_story_context,
)
from src.core.novels.services.generation.state import NextSceneSlot, NovelState
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ContinuationPlan:
    """Результат read-фазы: снапшот и что с ним делать.

    ``existing`` — сцена уже записана (её реплики проверяет ``_generate``);
    ``slot`` — слота ещё нет, нужен полный пайплайн. Ровно одно из полей задано.
    """

    state: NovelState
    existing: Scene | None = None
    slot: NextSceneSlot | None = None


class SceneContinuationService:
    """Догенерация новеллы: сцена шага роадмапа (roadmap_id, position) с репликами.

    Блокировка ``(novel_id, roadmap_id, position)`` держится вызывающим (use-case)
    на Redis, а генераторы сами делят работу на короткие read/write-транзакции и не
    держат соединение Postgres во время LLM-вызовов. При сбое частично созданная
    сцена удаляется каскадом (компенсация).
    """

    def __init__(
        self,
        novel_repository: NovelRepositoryProtocol,
        roadmap_repository: RoadmapRepositoryProtocol,
        scene_repository: SceneRepositoryProtocol,
        dialogue_line_repository: DialogueLineRepositoryProtocol,
        roadmap_choice_repository: RoadmapChoiceRepositoryProtocol,
        player_choice_repository: PlayerChoiceRepositoryProtocol,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
    ):
        self._novels = novel_repository
        self._roadmaps = roadmap_repository
        self._scenes = scene_repository
        self._dialogue_lines = dialogue_line_repository
        self._roadmap_choices = roadmap_choice_repository
        self._player_choices = player_choice_repository
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator

    async def generate(
        self,
        novel_id: int,
        roadmap_id: int,
        position: int,
        *,
        step: TransactionFactory,
    ) -> Scene:
        with llm_trace(f"scene_{roadmap_id}_{position}", novel_id=novel_id):
            return await self._generate(novel_id, roadmap_id, position, step=step)

    async def _generate(
        self,
        novel_id: int,
        roadmap_id: int,
        position: int,
        *,
        step: TransactionFactory,
    ) -> Scene:
        """Возвращает сцену. Read-фаза коммитится отдельно (``step``)."""
        plan = await self._read_plan(novel_id, roadmap_id, position, step=step)
        if plan.existing is not None:
            if not plan.state.scene_has_lines(plan.existing.id):
                await self._fill_dialogue(plan.existing, plan.state, step=step)
            return plan.existing
        if plan.slot is None:
            raise NovelFinishedError(novel_id)
        return await self._run_pipeline(plan.slot, plan.state, step=step)

    async def _read_plan(
        self,
        novel_id: int,
        roadmap_id: int,
        position: int,
        *,
        step: TransactionFactory,
    ) -> _ContinuationPlan:
        """Прочитать снапшот и решить, что генерировать (без вызовов LLM)."""
        async with step():
            if await self._novels.get_by_id(novel_id) is None:
                raise NovelNotFoundError(novel_id)

            state = await self._load_state(novel_id)

            # Идемпотентность по (roadmap_id, position): повторная доставка
            # возвращает готовую сцену. Сцена без реплик не готова — воркер упал
            # между её записью и диалогом; дописываем диалог (вне транзакции).
            existing = state.scene_at_step_position(roadmap_id, position)
            if existing is not None:
                return _ContinuationPlan(state=state, existing=existing)

            slot = state.resolve_next_slot()
            if slot is None:
                raise NovelFinishedError(novel_id)
            if slot.roadmap.id != roadmap_id or slot.position != position:
                raise SceneOrderError(
                    novel_id,
                    f"roadmap={roadmap_id},position={position}",
                    f"roadmap={slot.roadmap.id},position={slot.position}",
                )

            # Сцена коммитится до генерации диалога: шаг мог «закрыться» по числу
            # сцен, пока предыдущая сцена ещё без реплик. Не генерируем поверх неё.
            incomplete = state.first_scene_without_lines_before(slot.order)
            if incomplete is not None:
                raise SceneOrderError(
                    novel_id,
                    f"roadmap={roadmap_id},position={position}",
                    f"scene order={incomplete.order} (without dialogue)",
                )

            return _ContinuationPlan(state=state, slot=slot)

    async def _load_state(self, novel_id: int) -> NovelState:
        roadmaps = await self._roadmaps.list_by_novel_id(novel_id)
        scenes = await self._scenes.list_by_novel_id(novel_id)
        lines = await self._dialogue_lines.list_by_novel_id(novel_id)
        choices = await self._roadmap_choices.list_by_novel_id(novel_id)
        player_choices = await self._player_choices.list_by_novel_id(novel_id)
        return NovelState(
            roadmaps=roadmaps,
            scenes=scenes,
            dialogue_lines=lines,
            choices=choices,
            player_choices=player_choices,
        )

    async def _run_pipeline(
        self, slot: NextSceneSlot, state: NovelState, *, step: TransactionFactory
    ) -> Scene:
        story_text = render_story_context(
            state.last_story_context_before(slot.order)
        )

        scene: Scene | None = None
        try:
            scene = await self._scene_generator.generate(
                slot.roadmap.id,
                previous_scenes=state.last_scenes_before(slot.order),
                story_context=story_text,
                position=slot.position,
                order=slot.order,
                step=step,
            )

            if scene.needs_review:
                return scene

            await self._fill_dialogue(scene, state, step=step)
            return scene
        except Exception:
            # Компенсация: сцена уже закоммичена, а диалог/контекст не доехали —
            # удаляем её (СУБД каскадно убирает реплики), чтобы ретрай начал с чистого листа.
            if scene is not None:
                try:
                    async with step():
                        await self._scenes.delete(scene.id)
                except Exception:
                    logger.exception(
                        "Scene generation compensation failed for scene %s",
                        scene.id,
                    )
            raise

    async def _fill_dialogue(
        self, scene: Scene, state: NovelState, *, step: TransactionFactory
    ) -> None:
        """Записать реплики и изложение для уже закоммиченной сцены.

        Вызывается и для новой сцены, и для сцены без реплик после падения воркера.
        Контекст берётся из ``state`` строго до ``scene.order``: если «сирота» не
        последняя, глобальный хвост снапшота содержал бы сцены из будущего.
        """
        story_text = render_story_context(
            state.last_story_context_before(scene.order)
        )
        previous_scenes = state.last_scenes_before(scene.order)

        await self._dialogue_generator.generate(
            scene.id,
            previous_lines=state.previous_dialogue_lines_before(scene.order),
            story_context=story_text,
            all_lines=state.dialogue_lines_before(scene.order),
            previous_scene=previous_scenes[-1] if previous_scenes else None,
            step=step,
        )

        # После финальной сцены контекст некому читать: его берёт только генерация
        # следующей сцены, а её не будет. Пропускаем вызов, чтобы не платить
        # за мёртвый контекст.
        if scene.is_final_for_novel:
            return

        await self._story_context_generator.generate(
            scene.id,
            previous_context=state.last_story_context_before(scene.order),
            step=step,
        )

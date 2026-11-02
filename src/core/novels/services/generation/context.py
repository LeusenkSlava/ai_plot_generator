"""Загрузка контекста сцены для генерации диалога (только чтение).

``DialogueContextLoader`` — единственное место, где прод и инструмент перегенерации
читают контекст сцены из БД. ``load`` возвращает read-фазу ``DialogueGenerator``
(сцена, роадмап, новелла, каст, последние наряды, шаблон), а ``load_context``
дополнительно реконструирует из БД историю, которую прод получает из ``NovelState``
(прошлые реплики, изложение, использованные фразы, предыдущая сцена) — это нужно
инструменту, когда он пересобирает промпт уже сгенерированной сцены.

Ассеты (Codex) сюда не входят: это отдельная HTTP-фаза ``SceneAssetService``.
"""

from dataclasses import dataclass

from src.core.novels.exceptions import GenerationError
from src.core.novels.models import (
    DEFAULT_PROMPT_VARIANT,
    Character,
    Novel,
    Prompt,
    PromptKey,
    Roadmap,
    Scene,
)
from src.core.novels.services.crud import (
    CharacterService,
    DialogueLineService,
    NovelService,
    PlayerChoiceService,
    RoadmapChoiceService,
    RoadmapService,
    SceneService,
)
from src.core.novels.services.generation.prompts.cast import find_protagonist
from src.core.novels.services.generation.prompts.catalog import PromptCatalog
from src.core.novels.services.generation.prompts.dialogue import DialoguePromptContext
from src.core.novels.services.generation.state import NovelState
from src.core.novels.services.generation.story_state import (
    extract_used_phrases,
    render_story_context,
)


@dataclass(frozen=True, slots=True)
class DialogueReadPhase:
    """Read-фаза ``DialogueGenerator.generate``: всё, что читается из БД."""

    scene: Scene
    roadmap: Roadmap
    novel: Novel
    characters: list[Character]  # участники сцены
    all_characters: list[Character]  # весь каст
    last_outfits: dict[int, str]
    template: Prompt
    # Позиция сцены внутри шага и запланированное число сцен шага (1..N).
    scene_position: int = 0
    scenes_count: int = 0


class DialogueContextLoader:
    """Читает контекст сцены из БД (без Codex и без записи)."""

    def __init__(
        self,
        novel_service: NovelService,
        scene_service: SceneService,
        roadmap_service: RoadmapService,
        character_service: CharacterService,
        dialogue_line_service: DialogueLineService,
        prompt_catalog: PromptCatalog,
        roadmap_choice_service: RoadmapChoiceService | None = None,
        player_choice_service: PlayerChoiceService | None = None,
    ):
        self._novel_service = novel_service
        self._scene_service = scene_service
        self._roadmap_service = roadmap_service
        self._character_service = character_service
        self._dialogue_line_service = dialogue_line_service
        self._prompt_catalog = prompt_catalog
        # Сервисы выбора нужны только для полного ``NovelState`` в ``load_context``;
        # ``load`` (read-фаза прода) их не использует, поэтому они опциональны.
        self._roadmap_choice_service = roadmap_choice_service
        self._player_choice_service = player_choice_service

    @property
    def prompt_catalog(self) -> PromptCatalog:
        """Каталог промптов, которым loader резолвит шаблон.

        Нужен инструментам (тест промпта), чтобы запросить активный шаблон для
        варианта, отличного от ``novel.prompt_variant``.
        """
        return self._prompt_catalog

    async def load(self, scene_id: int) -> DialogueReadPhase:
        """Read-фаза генерации диалога: сцена, роадмап, новелла, каст, наряды, шаблон."""
        scene = await self._scene_service.get(scene_id)
        if not scene:
            raise GenerationError(f"Scene with id {scene_id} not found")

        roadmap = await self._roadmap_service.get(scene.roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {scene.roadmap_id} not found")

        characters, all_characters = await self._scene_cast(scene, roadmap.novel_id)
        if not characters:
            raise GenerationError(f"No characters found for novel {roadmap.novel_id}")

        novel = await self._novel_service.get(roadmap.novel_id)

        last_outfits = await self._dialogue_line_service.last_outfit_per_character(
            roadmap.novel_id
        )

        template = await self._prompt_catalog.get(
            PromptKey.DIALOGUE,
            novel.prompt_variant if novel else DEFAULT_PROMPT_VARIANT,
        )

        # Позиция сцены внутри шага: по ней диалог понимает, завязка это или
        # сцена, которая обязана дойти до смены шага (акт, развязка). Считаем
        # так же, как next_scene_position: только валидные сцены (needs_review
        # не закрывают шаг и не должны сдвигать нумерацию).
        roadmap_scenes = await self._scene_service.list_by_roadmap(roadmap.id) or []
        ordered = sorted(
            (s for s in roadmap_scenes if not s.needs_review), key=lambda s: s.order
        )
        scene_position = next(
            (position for position, s in enumerate(ordered, start=1) if s.id == scene.id),
            0,
        )
        scenes_count = roadmap.scenes_count or len(ordered)

        return DialogueReadPhase(
            scene=scene,
            roadmap=roadmap,
            novel=novel,
            characters=characters,
            all_characters=all_characters,
            last_outfits=last_outfits,
            template=template,
            scene_position=scene_position,
            scenes_count=scenes_count,
        )

    async def load_context(
        self, scene_id: int, read: DialogueReadPhase | None = None
    ) -> DialoguePromptContext:
        """Полный контекст промпта для инструмента: read-фаза + реконструкция истории.

        Строит тот же ``NovelState``, что и прод (``SceneContinuationService._load_state``),
        но на снапшоте «до генерации этой сцены»: прод читает состояние до того, как сцена
        и её реплики созданы, поэтому реконструкция исключает саму сцену и всё, что
        сгенерировано после неё. Способ сборки истории берётся целиком из свойств
        ``NovelState`` (``last_scenes``, ``last_story_context``, ``previous_dialogue_lines``),
        а не дублируется здесь. ``assets`` и ``current_outfits`` не заполняются —
        инструмент тестирует текст без визуала.
        """
        if read is None:
            read = await self.load(scene_id)

        novel_id = read.novel.id
        scenes = await self._scene_service.list_by_novel(novel_id) or []
        lines = await self._dialogue_line_service.list_by_novel(novel_id) or []

        # Снапшот «до генерации этой сцены»: в порядке проигрывания остаётся только
        # то, что идёт раньше неё — сама сцена и всё после неё ещё не существовали.
        scene_order = read.scene.order
        order_by_id = {s.id: s.order for s in scenes}
        prior_scenes = [s for s in scenes if s.order < scene_order]
        prior_lines = [
            line
            for line in lines
            if line.scene_id != read.scene.id
            and order_by_id.get(line.scene_id, 0) < scene_order
        ]

        state = NovelState(
            roadmaps=await self._roadmap_service.list_by_novel(novel_id) or [],
            scenes=prior_scenes,
            dialogue_lines=prior_lines,
            choices=(
                await self._roadmap_choice_service.list_by_novel(novel_id)
                if self._roadmap_choice_service
                else []
            ),
            player_choices=(
                await self._player_choice_service.list_by_novel(novel_id)
                if self._player_choice_service
                else []
            ),
        )

        return DialoguePromptContext(
            scene=read.scene,
            roadmap=read.roadmap,
            characters=read.characters,
            all_characters=read.all_characters,
            protagonist=find_protagonist(read.characters),
            assets=None,
            previous_lines=state.previous_dialogue_lines,
            story_context=render_story_context(state.last_story_context),
            current_outfits="",
            used_phrases=extract_used_phrases(
                [line.text for line in state.dialogue_lines],
                [c.name for c in read.all_characters],
            ),
            previous_scene=state.last_scenes[-1] if state.last_scenes else None,
            scene_position=read.scene_position,
            scenes_count=read.scenes_count,
        )

    async def _scene_cast(
        self, scene: Scene, novel_id: int
    ) -> tuple[list[Character], list[Character]]:
        """Персонажи, присутствующие в сцене, и весь каст новеллы.

        Список «кто в сцене» формирует SceneGenerator (scene.character_ids) по месту/времени
        шага. Если список пуст (старая сцена без списка), возвращаем весь каст — обратная
        совместимость с уже сгенерированными сценами. Весь каст нужен отдельно, чтобы
        подписывать имена в «последних репликах» даже для персонажей не из текущей сцены.
        """
        all_characters = await self._character_service.list_by_novel(novel_id) or []
        if not scene.character_ids:
            return all_characters, all_characters
        ids = set(scene.character_ids)
        return [c for c in all_characters if c.id in ids], all_characters

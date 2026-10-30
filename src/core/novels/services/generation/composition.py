import logging

from src.core.novels.exceptions import GenerationError, NovelGenerationFailedError
from src.core.novels.llm_trace import llm_trace
from src.core.novels.models import Novel
from src.core.novels.services.generation.generators.character import CharacterGenerator
from src.core.novels.services.generation.generators.dialogue import DialogueGenerator
from src.core.novels.services.generation.generators.novel import NovelGenerator
from src.core.novels.services.generation.generators.roadmap import RoadmapGenerator
from src.core.novels.services.generation.generators.scene import SceneGenerator
from src.core.novels.services.generation.generators.story_context import (
    StoryContextGenerator,
)
from src.core.novels.services.generation.transactions import TransactionFactory

logger = logging.getLogger(__name__)


class NovelCompositionService:
    def __init__(
        self,
        novel_generator: NovelGenerator,
        character_generator: CharacterGenerator,
        roadmap_generator: RoadmapGenerator,
        scene_generator: SceneGenerator,
        dialogue_generator: DialogueGenerator,
        story_context_generator: StoryContextGenerator,
    ):
        self._novel_generator = novel_generator
        self._character_generator = character_generator
        self._roadmap_generator = roadmap_generator
        self._scene_generator = scene_generator
        self._dialogue_generator = dialogue_generator
        self._story_context_generator = story_context_generator

    async def create(
        self,
        user_promt: str,
        universe_id: int | None = None,
        *,
        step: TransactionFactory,
    ) -> Novel:
        """Сага генерации новеллы: каждый шаг — отдельная транзакция (``step``).

        Генераторы сами разбивают работу на короткие read/write-транзакции, а LLM
        вызывают между ними, поэтому соединение Postgres не держится во время
        генерации. При сбое после первого шага бросаем ``NovelGenerationFailedError``
        с id уже созданной новеллы — вызывающий выполнит компенсацию (удаление).
        """
        novel: Novel | None = None
        try:
            with llm_trace("create_novel") as trace:
                novel = await self._novel_generator.generate(
                    user_promt,
                    universe_id=universe_id,
                    step=step,
                )
                trace.bind(novel.id)

                await self._character_generator.generate(novel.id, step=step)

                roadmap = await self._roadmap_generator.generate(novel.id, step=step)

                # Первая сцена — отдельный признак, не разовая настройка.
                with llm_trace("scene_1", novel_id=novel.id):
                    first_step = roadmap[0]
                    scene = await self._scene_generator.generate(first_step.id, step=step)
                    if scene.needs_review:
                        return novel

                    await self._dialogue_generator.generate(scene.id, step=step)

                    # Для финальной сцены контекст никому не нужен — следующей сцены не будет.
                    if scene.is_final_for_novel:
                        return novel

                    # Для первой сцены изложения ещё нет — собираем его только из её диалога
                    await self._story_context_generator.generate(scene.id, step=step)

            return novel
        except GenerationError as e:
            raise NovelGenerationFailedError(
                novel.id if novel else None, str(e) or "Generation failed"
            ) from e
        except Exception as e:
            # Любой сбой после первого шага (в т.ч. DB-ошибка на одном из write-шагов,
            # которая не является GenerationError) должен обернуться так же, чтобы
            # use-case выполнил компенсацию и не оставил частично созданную новеллу.
            logger.exception(
                "Novel composition failed with non-generation error (novel_id=%s)",
                novel.id if novel else None,
            )
            raise NovelGenerationFailedError(
                novel.id if novel else None, str(e) or "Generation failed"
            ) from e

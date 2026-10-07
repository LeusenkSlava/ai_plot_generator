import logging

from src.core.novels.exceptions import GenerationError
from src.core.novels.interfaces.generation import GeneratorProtocol
from src.core.novels.models import Novel, Roadmap, Scene
from src.core.novels.services.crud import NovelService, RoadmapService, SceneService
from src.core.novels.services.generate.base import BaseGenerator

logger = logging.getLogger(__name__)


class SceneGenerator(BaseGenerator):
    def __init__(
        self,
        novel_service: NovelService,
        roadmap_service: RoadmapService,
        scene_service: SceneService,
        generator: GeneratorProtocol,
    ):
        super().__init__(generator)
        self._novel_service = novel_service
        self._roadmap_service = roadmap_service
        self._scene_service = scene_service

    async def generate(
        self,
        roadmap_id: int,
        previous_scenes: list[Scene] | None = None,
        story_context: str | None = None,
        order: int | None = None,
    ) -> Scene:
        """Следующая сцена шага роадмапа. previous_scenes — уже сыгранные сцены новеллы для связности,
        story_context — изложение истории после предыдущей сцены. order — сквозной номер сцены в новелле."""
        roadmap = await self._roadmap_service.get(roadmap_id)
        if not roadmap:
            raise GenerationError(f"Roadmap with id {roadmap_id} not found")

        novel = await self._novel_service.get(roadmap.novel_id)
        if not novel:
            raise GenerationError(f"Novel with id {roadmap.novel_id} not found")

        # Позиция сцены внутри шага роадмапа (для финала шага и подсказки в промпте).
        step_position = len(
            await self._scene_service.list_by_roadmap(roadmap.id) or []
        ) + 1
        # Сквозной номер сцены по всей новелле: по нему идёт идемпотентность и
        # упорядочивание в NovelState, поэтому он не должен сбрасываться на каждом шаге.
        if order is None:
            order = len(await self._scene_service.list_by_novel(novel.id) or []) + 1
        is_final_for_roadmap = step_position >= max(roadmap.scenes_count, 1)
        roadmaps = await self._roadmap_service.list_by_novel(novel.id) or []
        is_last_roadmap = roadmap.step_id >= max(
            (r.step_id for r in roadmaps), default=0
        )

        prompt = self.__create_prompt(
            novel, roadmap, step_position, previous_scenes or [], story_context
        )
        data = await self._generate(prompt, think=False)

        scene = Scene(
            id=None,
            created_at=None,
            updated_at=None,
            roadmap_id=roadmap.id,
            title=data["title"],
            description=data["description"],
            order=order,
            is_final_for_roadmap=is_final_for_roadmap,
            is_final_for_novel=is_final_for_roadmap and is_last_roadmap,
        )
        scene = await self._scene_service.add(scene)
        return scene

    def __create_prompt(
        self,
        novel: Novel,
        roadmap: Roadmap,
        step_position: int,
        previous_scenes: list[Scene],
        story_context: str | None,
    ) -> list[dict]:
        scenes_count = max(roadmap.scenes_count, step_position)
        system_prompt = {
            "role": "system",
            "content": (
                "Ты сценарист интерактивных визуальных новелл. "
                "На основе описания истории и текущего шага роадмапа создай очередную сцену этого шага. "
                "Она должна продолжать предыдущие сцены, не повторяя их, "
                "и продвигать сюжет к цели шага. "
                "Сцена должна раскрывать цель шага и задавать место и ситуацию действия, "
                "но не пересказывать сами диалоги. Укажи:\n"
                "1. title - короткое название сцены.\n"
                "2. description - описание места, времени, ситуации и конфликта сцены, "
                "на основе которого дальше будут сгенерированы диалоги персонажей: "
                "2-4 предложения, не больше 400 символов, без атмосферных подробностей.\n"
                "Отвечай СТРОГО в формате JSON, соответствующего этой схеме:\n"
                """
                {
                  "title": string,
                  "description": string
                }
                """
            ),
        }
        # Сначала неизменное для новеллы, потом меняющееся: так работает кеш префикса у провайдера
        user_content = (
            f"Название истории: {novel.title}\n" f"Тон повествования: {novel.tone}"
        )
        if story_context:
            user_content += (
                "\n\nИзложение истории на данный момент (сцена не должна ему противоречить; "
                f"одежду персонажей не меняй без сюжетной причины):\n{story_context}"
            )
        if previous_scenes:
            # Что произошло, уже есть в изложении — полностью нужна только последняя сцена для стыка
            *earlier, last = previous_scenes
            story_so_far = "".join(f"- {scene.title}\n" for scene in earlier)
            story_so_far += f"- {last.title}: {last.description}"
            user_content += f"\n\nПредыдущие сцены:\n{story_so_far}"
        user_content += (
            f"\n\nШаг роадмапа: {roadmap.title}\n"
            f"Цель шага: {roadmap.goal}\n"
            f"Номер сцены в шаге: {step_position} из {scenes_count}"
        )
        user_prompt = {"role": "user", "content": user_content}
        return [system_prompt, user_prompt]

from src.core.novels.interfaces.repository import (
    CharacterRepositoryProtocol,
    DialogueActionRepositoryProtocol,
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import (
    Character,
    DialogueAction,
    DialogueLine,
    Novel,
    Roadmap,
    Scene,
)


class CharacterService:

    def __init__(self, repository: CharacterRepositoryProtocol):
        self._repository = repository

    async def add(self, character: Character) -> Character:
        character = await self._repository.add(character)
        return character

    async def get(self, character_id: int) -> Character | None:
        character = await self._repository.get_by_id(character_id)
        return character

    async def list_by_novel(self, novel_id: int) -> list[Character] | None:
        characters = await self._repository.list_by_novel_id(novel_id)
        return characters

    async def delete(self, character_id: int) -> None:
        await self._repository.delete(character_id)


class RoadmapService:
    def __init__(self, repository: RoadmapRepositoryProtocol):
        self._repository = repository

    async def add(self, roadmap: Roadmap) -> Roadmap:
        roadmap = await self._repository.add(roadmap)
        return roadmap

    async def get(self, roadmap_id: int) -> Roadmap | None:
        roadmap = await self._repository.get_by_id(roadmap_id)
        return roadmap

    async def list_by_novel(self, novel_id: int) -> list[Roadmap] | None:
        roadmaps = await self._repository.list_by_novel_id(novel_id)
        return roadmaps

    async def delete(self, roadmap_id: int) -> None:
        await self._repository.delete(roadmap_id)


class SceneService:
    def __init__(self, repository: SceneRepositoryProtocol):
        self._repository = repository

    async def add(self, scene: Scene) -> Scene:
        scene = await self._repository.add(scene)
        return scene

    async def get(self, scene_id: int) -> Scene | None:
        scene = await self._repository.get_by_id(scene_id)
        return scene

    async def list_by_roadmap(self, roadmap_id: int) -> list[Scene] | None:
        scenes = await self._repository.list_by_roadmap_id(roadmap_id)
        return scenes

    async def list_by_novel(self, novel_id: int) -> list[Scene] | None:
        scenes = await self._repository.list_by_novel_id(novel_id)
        return scenes

    async def update_story_context(self, scene_id: int, story_context: str) -> None:
        await self._repository.update_story_context(scene_id, story_context)

    async def delete(self, scene_id: int) -> None:
        await self._repository.delete(scene_id)


class NovelService:
    def __init__(self, repository: NovelRepositoryProtocol):
        self._repository = repository

    async def add(self, novel: Novel) -> Novel:
        novel = await self._repository.add(novel)
        return novel

    async def get(self, novel_id: int) -> Novel | None:
        novel = await self._repository.get_by_id(novel_id)
        return novel

    async def list(self, limit: int, offset: int) -> tuple[list[Novel], int]:
        novels = await self._repository.list_all(limit=limit, offset=offset)
        total = await self._repository.count()
        return novels, total

    async def delete(self, novel_id: int) -> None:
        await self._repository.delete(novel_id)


class DialogueLineService:
    def __init__(self, repository: DialogueLineRepositoryProtocol):
        self._repository = repository

    async def add(self, dialog_line: DialogueLine) -> DialogueLine:
        dialog_line = await self._repository.add(dialog_line)
        return dialog_line

    async def get(self, dialog_line_id: int) -> DialogueLine | None:
        dialog_line = await self._repository.get_by_id(dialog_line_id)
        return dialog_line

    async def list_by_novel(self, novel_id: int) -> list[DialogueLine] | None:
        dialog_line = await self._repository.list_by_novel_id(novel_id)
        return dialog_line

    async def list_by_scene(self, scene_id: int) -> list[DialogueLine]:
        return await self._repository.list_by_scene_id(scene_id)

    async def last_outfit_per_character(self, novel_id: int) -> dict[int, str]:
        return await self._repository.last_outfit_per_character(novel_id)

    async def delete(self, dialog_line_id: int) -> None:
        await self._repository.delete(dialog_line_id)


class DialogueActionService:
    def __init__(self, repository: DialogueActionRepositoryProtocol):
        self._repository = repository

    async def add(self, dialog_action: DialogueAction) -> DialogueAction:
        dialog_action = await self._repository.add(dialog_action)
        return dialog_action

    async def get(self, dialog_action_id: int) -> DialogueAction | None:
        dialog_action = await self._repository.get_by_id(dialog_action_id)
        return dialog_action

    async def delete(self, dialog_action_id: int) -> None:
        await self._repository.delete(dialog_action_id)

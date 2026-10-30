from src.core.novels.interfaces.repository import (
    CharacterRepositoryProtocol,
    DialogueLineRepositoryProtocol,
    NovelRepositoryProtocol,
    PlayerChoiceRepositoryProtocol,
    RoadmapChoiceRepositoryProtocol,
    RoadmapRepositoryProtocol,
    SceneRepositoryProtocol,
)
from src.core.novels.models import (
    Character,
    DialogueLine,
    Novel,
    PlayerChoice,
    Roadmap,
    RoadmapChoice,
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


class RoadmapChoiceService:
    def __init__(self, repository: RoadmapChoiceRepositoryProtocol):
        self._repository = repository

    async def add(self, choice: RoadmapChoice) -> RoadmapChoice:
        return await self._repository.add(choice)

    async def get(self, choice_id: int) -> RoadmapChoice | None:
        return await self._repository.get_by_id(choice_id)

    async def list_by_roadmap(self, roadmap_id: int) -> list[RoadmapChoice]:
        return await self._repository.list_by_roadmap_id(roadmap_id)

    async def list_by_novel(self, novel_id: int) -> list[RoadmapChoice]:
        return await self._repository.list_by_novel_id(novel_id)

    async def update_next_roadmap(self, choice_id: int, next_roadmap_id: int) -> None:
        await self._repository.update_next_roadmap(choice_id, next_roadmap_id)

    async def delete(self, choice_id: int) -> None:
        await self._repository.delete(choice_id)


class PlayerChoiceService:
    def __init__(self, repository: PlayerChoiceRepositoryProtocol):
        self._repository = repository

    async def add(self, player_choice: PlayerChoice) -> PlayerChoice:
        return await self._repository.add(player_choice)

    async def get(self, player_choice_id: int) -> PlayerChoice | None:
        return await self._repository.get_by_id(player_choice_id)

    async def list_by_novel(self, novel_id: int) -> list[PlayerChoice]:
        return await self._repository.list_by_novel_id(novel_id)

    async def get_by_roadmap_choice(
        self, roadmap_choice_id: int
    ) -> PlayerChoice | None:
        return await self._repository.get_by_roadmap_choice_id(roadmap_choice_id)

    async def delete(self, player_choice_id: int) -> None:
        await self._repository.delete(player_choice_id)

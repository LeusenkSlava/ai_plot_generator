from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.novels.models import (
    Character,
    DialogueAction,
    DialogueLine,
    Novel,
    Roadmap,
    Scene,
)
from src.outbound.database.models.novels import (
    CharacterModel,
    DialogueActionModel,
    DialogueLineModel,
    NovelModel,
    RoadmapModel,
    SceneModel,
)


class CharacterRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, character: Character) -> Character:
        db_character = CharacterModel(
            novel_id=character.novel_id,
            name=character.name,
            role=character.role,
            arc=character.arc,
            voice_notes=character.voice_notes,
            codex_character_id=character.codex_character_id,
        )
        self._session.add(db_character)
        await self._session.flush()
        return self._to_domain(db_character)

    async def get_by_id(self, character_id: int) -> Character | None:
        result = await self._session.execute(
            select(CharacterModel).where(CharacterModel.id == character_id)
        )
        db_character = result.scalar_one_or_none()
        return self._to_domain(db_character) if db_character else None

    async def list_by_novel_id(self, novel_id: int) -> list[Character]:
        result = await self._session.execute(
            select(CharacterModel).where(CharacterModel.novel_id == novel_id)
        )
        return [self._to_domain(c) for c in result.scalars().all()]

    async def delete(self, character_id: int) -> None:
        db_character = await self._session.get(CharacterModel, character_id)
        if db_character:
            await self._session.delete(db_character)

    @staticmethod
    def _to_domain(db_character: CharacterModel) -> Character:
        return Character(
            id=db_character.id,
            created_at=db_character.created_at,
            updated_at=db_character.updated_at,
            novel_id=db_character.novel_id,
            name=db_character.name,
            role=db_character.role,
            arc=db_character.arc,
            voice_notes=db_character.voice_notes,
            codex_character_id=db_character.codex_character_id,
        )


class RoadmapRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, roadmap: Roadmap) -> Roadmap:
        db_roadmap = RoadmapModel(
            novel_id=roadmap.novel_id,
            step_id=roadmap.step_id,
            title=roadmap.title,
            goal=roadmap.goal,
            target_choice=roadmap.target_choice,
            choice_stakes=roadmap.choice_stakes,
            scenes_count=roadmap.scenes_count,
        )
        self._session.add(db_roadmap)
        await self._session.flush()
        return self._to_domain(db_roadmap)

    async def get_by_id(self, roadmap_id: int) -> Roadmap | None:
        result = await self._session.execute(
            select(RoadmapModel).where(RoadmapModel.id == roadmap_id)
        )
        db_roadmap = result.scalar_one_or_none()
        return self._to_domain(db_roadmap) if db_roadmap else None

    async def list_by_novel_id(self, novel_id: int) -> list[Roadmap]:
        result = await self._session.execute(
            select(RoadmapModel)
            .where(RoadmapModel.novel_id == novel_id)
            .order_by(RoadmapModel.step_id)
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def delete(self, roadmap_id: int) -> None:
        db_roadmap = await self._session.get(RoadmapModel, roadmap_id)
        if db_roadmap:
            await self._session.delete(db_roadmap)

    @staticmethod
    def _to_domain(db_roadmap: RoadmapModel) -> Roadmap:
        return Roadmap(
            id=db_roadmap.id,
            created_at=db_roadmap.created_at,
            updated_at=db_roadmap.updated_at,
            novel_id=db_roadmap.novel_id,
            step_id=db_roadmap.step_id,
            title=db_roadmap.title,
            goal=db_roadmap.goal,
            target_choice=db_roadmap.target_choice,
            choice_stakes=db_roadmap.choice_stakes,
            scenes_count=db_roadmap.scenes_count,
        )


class SceneRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, scene: Scene) -> Scene:
        db_scene = SceneModel(
            roadmap_id=scene.roadmap_id,
            title=scene.title,
            description=scene.description,
            order=scene.order,
            is_final_for_roadmap=scene.is_final_for_roadmap,
            is_final_for_novel=scene.is_final_for_novel,
            story_context=scene.story_context,
        )
        self._session.add(db_scene)
        await self._session.flush()
        return self._to_domain(db_scene)

    async def get_by_id(self, scene_id: int) -> Scene | None:
        result = await self._session.execute(
            select(SceneModel).where(SceneModel.id == scene_id)
        )
        db_scene = result.scalar_one_or_none()
        return self._to_domain(db_scene) if db_scene else None

    async def list_by_roadmap_id(self, roadmap_id: int) -> list[Scene]:
        result = await self._session.execute(
            select(SceneModel)
            .where(SceneModel.roadmap_id == roadmap_id)
            .order_by(SceneModel.order)
        )
        return [self._to_domain(s) for s in result.scalars().all()]

    async def list_by_novel_id(self, novel_id: int) -> list[Scene]:
        """Все сцены новеллы по порядку: шаг роадмапа -> сцена."""
        result = await self._session.execute(
            select(SceneModel)
            .join(RoadmapModel, RoadmapModel.id == SceneModel.roadmap_id)
            .where(RoadmapModel.novel_id == novel_id)
            .order_by(RoadmapModel.step_id, SceneModel.order, SceneModel.id)
        )
        return [self._to_domain(s) for s in result.scalars().all()]

    async def update_story_context(self, scene_id: int, story_context: str) -> None:
        db_scene = await self._session.get(SceneModel, scene_id)
        if db_scene:
            db_scene.story_context = story_context
            await self._session.flush()

    async def delete(self, scene_id: int) -> None:
        db_scene = await self._session.get(SceneModel, scene_id)
        if db_scene:
            await self._session.delete(db_scene)

    @staticmethod
    def _to_domain(db_scene: SceneModel) -> Scene:
        return Scene(
            id=db_scene.id,
            created_at=db_scene.created_at,
            updated_at=db_scene.updated_at,
            roadmap_id=db_scene.roadmap_id,
            title=db_scene.title,
            description=db_scene.description,
            order=db_scene.order,
            is_final_for_roadmap=db_scene.is_final_for_roadmap,
            is_final_for_novel=db_scene.is_final_for_novel,
            story_context=db_scene.story_context,
        )


class NovelRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, novel: Novel) -> Novel:
        db_novel = NovelModel(
            title=novel.title,
            public_description=novel.public_description,
            description=novel.description,
            tone=novel.tone,
            universe_id=novel.universe_id,
        )
        self._session.add(db_novel)
        await self._session.flush()
        return self._to_domain(db_novel)

    async def get_by_id(self, novel_id: int) -> Novel | None:
        result = await self._session.execute(
            select(NovelModel).where(NovelModel.id == novel_id)
        )
        db_novel = result.scalar_one_or_none()
        return self._to_domain(db_novel) if db_novel else None

    async def list_all(self, limit: int, offset: int) -> list[Novel]:
        result = await self._session.execute(
            select(NovelModel)
            .order_by(NovelModel.created_at.desc(), NovelModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(n) for n in result.scalars().all()]

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(NovelModel)
        )
        return result.scalar_one()

    async def delete(self, novel_id: int) -> None:
        db_novel = await self._session.get(NovelModel, novel_id)
        if db_novel:
            await self._session.delete(db_novel)

    @staticmethod
    def _to_domain(db_novel: NovelModel) -> Novel:
        return Novel(
            id=db_novel.id,
            title=db_novel.title,
            public_description=db_novel.public_description,
            description=db_novel.description,
            tone=db_novel.tone,
            universe_id=db_novel.universe_id,
            created_at=db_novel.created_at,
            updated_at=db_novel.updated_at,
        )


class DialogueLineRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, dialog_line: DialogueLine) -> DialogueLine:
        db_dialog_line = DialogueLineModel(
            novel_id=dialog_line.novel_id,
            scene_id=dialog_line.scene_id,
            character_id=dialog_line.character_id,
            order=dialog_line.order,
            text=dialog_line.text,
            is_final_for_scene=dialog_line.is_final_for_scene,
            background_asset_key=dialog_line.background_asset_key,
            sprite_asset_key=dialog_line.sprite_asset_key,
            outfit_asset_key=dialog_line.outfit_asset_key,
            emotion_asset_key=dialog_line.emotion_asset_key,
        )
        self._session.add(db_dialog_line)
        await self._session.flush()
        return self._to_domain(db_dialog_line)

    async def get_by_id(self, dialog_line_id: int) -> DialogueLine | None:
        result = await self._session.execute(
            select(DialogueLineModel).where(DialogueLineModel.id == dialog_line_id)
        )
        db_dialog_line = result.scalar_one_or_none()
        return self._to_domain(db_dialog_line) if db_dialog_line else None

    async def list_by_novel_id(self, novel_id) -> list[DialogueLine]:
        """Все реплики новеллы в порядке проигрывания: шаг роадмапа -> сцена -> реплика."""
        result = await self._session.execute(
            select(DialogueLineModel)
            .join(SceneModel, SceneModel.id == DialogueLineModel.scene_id)
            .join(RoadmapModel, RoadmapModel.id == SceneModel.roadmap_id)
            .where(DialogueLineModel.novel_id == novel_id)
            .order_by(
                RoadmapModel.step_id,
                SceneModel.order,
                DialogueLineModel.order,
                DialogueLineModel.id,
            )
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def list_by_scene_id(self, scene_id: int) -> list[DialogueLine]:
        result = await self._session.execute(
            select(DialogueLineModel)
            .where(DialogueLineModel.scene_id == scene_id)
            .order_by(DialogueLineModel.order)
        )
        return [self._to_domain(r) for r in result.scalars().all()]

    async def delete(self, dialog_line_id: int) -> None:
        db_dialog_line = await self._session.get(DialogueLineModel, dialog_line_id)
        if db_dialog_line:
            await self._session.delete(db_dialog_line)

    @staticmethod
    def _to_domain(db_dialog_line: DialogueLineModel) -> DialogueLine:
        return DialogueLine(
            id=db_dialog_line.id,
            created_at=db_dialog_line.created_at,
            updated_at=db_dialog_line.updated_at,
            novel_id=db_dialog_line.novel_id,
            scene_id=db_dialog_line.scene_id,
            character_id=db_dialog_line.character_id,
            order=db_dialog_line.order,
            text=db_dialog_line.text,
            is_final_for_scene=db_dialog_line.is_final_for_scene,
            background_asset_key=db_dialog_line.background_asset_key,
            sprite_asset_key=db_dialog_line.sprite_asset_key,
            outfit_asset_key=db_dialog_line.outfit_asset_key,
            emotion_asset_key=db_dialog_line.emotion_asset_key,
        )


class DialogueActionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, dialog_action: DialogueAction) -> DialogueAction:
        db_dialog_action = DialogueActionModel(
            dialogue_line_id=dialog_action.dialogue_line_id,
            order=dialog_action.order,
            text=dialog_action.text,
            next_roadmap_id=dialog_action.next_roadmap_id,
        )
        self._session.add(db_dialog_action)
        await self._session.flush()
        return self._to_domain(db_dialog_action)

    async def get_by_id(self, dialog_action_id: int) -> DialogueAction | None:
        result = await self._session.execute(
            select(DialogueActionModel).where(
                DialogueActionModel.id == dialog_action_id
            )
        )
        db_dialog_action = result.scalar_one_or_none()
        return self._to_domain(db_dialog_action) if db_dialog_action else None

    async def delete(self, dialog_action_id: int) -> None:
        db_dialog_action = await self._session.get(
            DialogueActionModel, dialog_action_id
        )
        if db_dialog_action:
            await self._session.delete(db_dialog_action)

    @staticmethod
    def _to_domain(db_dialog_action: DialogueActionModel) -> DialogueAction:
        return DialogueAction(
            id=db_dialog_action.id,
            created_at=db_dialog_action.created_at,
            updated_at=db_dialog_action.updated_at,
            dialogue_line_id=db_dialog_action.dialogue_line_id,
            order=db_dialog_action.order,
            text=db_dialog_action.text,
            next_roadmap_id=db_dialog_action.next_roadmap_id,
        )

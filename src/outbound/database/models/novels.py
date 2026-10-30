from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.novels.models import NovelMode
from src.outbound.database.models.base_model import BaseModel
from src.outbound.database.utils import pg_enum


class CharacterModel(BaseModel):
    __tablename__ = "characters"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    arc: Mapped[str] = mapped_column(String, nullable=False)
    voice_notes: Mapped[str] = mapped_column(String, nullable=False)
    codex_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    is_protagonist: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    novel: Mapped["NovelModel"] = relationship(
        "NovelModel", back_populates="characters"
    )

    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel",
        back_populates="character",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<CharacterModel(id={self.id}, name={self.name}, novel_id={self.novel_id})>"


class RoadmapModel(BaseModel):
    __tablename__ = "roadmap"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)
    conflict: Mapped[str] = mapped_column(String, nullable=False)
    change: Mapped[str] = mapped_column(String, nullable=False)
    target_choice: Mapped[bool] = mapped_column(Boolean)
    choice_stakes: Mapped[str | None] = mapped_column(String)
    scenes_count: Mapped[int] = mapped_column(Integer, nullable=False)
    location_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String, nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_roadmap_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("roadmap.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    branch_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    novel: Mapped["NovelModel"] = relationship("NovelModel", back_populates="roadmap")

    scenes: Mapped[list["SceneModel"]] = relationship(
        "SceneModel",
        back_populates="roadmap",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SceneModel.order",
    )

    choices: Mapped[list["RoadmapChoiceModel"]] = relationship(
        "RoadmapChoiceModel",
        back_populates="roadmap",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RoadmapChoiceModel.roadmap_id",
        order_by="RoadmapChoiceModel.order",
    )

    def __repr__(self):
        return f"<RoadmapModel(id={self.id}, depth={self.depth}, novel_id={self.novel_id})>"


class NovelModel(BaseModel):
    __tablename__ = "novels"

    title: Mapped[str] = mapped_column(String, nullable=False)
    public_description: Mapped[str] = mapped_column(String, nullable=False)

    description: Mapped[str] = mapped_column(String, nullable=False)
    tone: Mapped[str] = mapped_column(String, nullable=False)
    universe_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[NovelMode] = mapped_column(
        pg_enum(NovelMode, native=False),
        nullable=False,
        default=NovelMode.LINEAR,
        server_default=NovelMode.LINEAR.value,
    )

    characters: Mapped[list["CharacterModel"]] = relationship(
        "CharacterModel", back_populates="novel", cascade="all, delete-orphan", passive_deletes=True
    )
    roadmap: Mapped[list["RoadmapModel"]] = relationship(
        "RoadmapModel",
        back_populates="novel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RoadmapModel.depth",
    )
    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel", back_populates="novel", cascade="all, delete-orphan", passive_deletes=True
    )


class SceneModel(BaseModel):
    __tablename__ = "scenes"

    roadmap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roadmap.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_final_for_roadmap: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_final_for_novel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    story_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Типизированный список id персонажей, присутствующих в сцене
    character_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    location_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String, nullable=True)
    day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    roadmap: Mapped["RoadmapModel"] = relationship(
        "RoadmapModel", back_populates="scenes"
    )

    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel",
        back_populates="scene",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DialogueLineModel.order",
    )

    def __repr__(self):
        return f"<SceneModel(id={self.id}, roadmap_id={self.roadmap_id}, order={self.order})>"


class DialogueLineModel(BaseModel):
    __tablename__ = "dialogue_lines"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String, nullable=False)
    is_final_for_scene: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_thought: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    background_asset_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sound_asset_key: Mapped[str | None] = mapped_column(String, nullable=True)
    sprite_asset_key: Mapped[str | None] = mapped_column(String, nullable=True)
    outfit_asset_key: Mapped[str | None] = mapped_column(String, nullable=True)
    emotion_asset_key: Mapped[str | None] = mapped_column(String, nullable=True)

    novel: Mapped["NovelModel"] = relationship(
        "NovelModel", back_populates="dialogue_lines"
    )
    scene: Mapped["SceneModel"] = relationship(
        "SceneModel", back_populates="dialogue_lines"
    )
    character: Mapped["CharacterModel"] = relationship(
        "CharacterModel", back_populates="dialogue_lines"
    )

    def __repr__(self):
        return f"<DialogueLineModel(id={self.id}, scene_id={self.scene_id}, character_id={self.character_id})>"


class RoadmapChoiceModel(BaseModel):
    __tablename__ = "roadmap_choices"

    roadmap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roadmap.id", ondelete="CASCADE"), nullable=False, index=True
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String, nullable=False)
    is_true: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    branch_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_roadmap_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("roadmap.id", ondelete="SET NULL"), nullable=True
    )

    roadmap: Mapped["RoadmapModel"] = relationship(
        "RoadmapModel",
        back_populates="choices",
        foreign_keys=[roadmap_id],
    )
    next_roadmap: Mapped["RoadmapModel"] = relationship(
        "RoadmapModel",
        foreign_keys=[next_roadmap_id],
    )

    def __repr__(self):
        return f"<RoadmapChoiceModel(id={self.id}, roadmap_id={self.roadmap_id}, is_true={self.is_true})>"


class PlayerChoiceModel(BaseModel):
    __tablename__ = "player_choices"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    roadmap_choice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roadmap_choices.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    dialogue_line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dialogue_lines.id", ondelete="SET NULL"), nullable=True
    )

    novel: Mapped["NovelModel"] = relationship("NovelModel")
    roadmap_choice: Mapped["RoadmapChoiceModel"] = relationship("RoadmapChoiceModel")

    def __repr__(self):
        return f"<PlayerChoiceModel(id={self.id}, novel_id={self.novel_id}, roadmap_choice_id={self.roadmap_choice_id})>"

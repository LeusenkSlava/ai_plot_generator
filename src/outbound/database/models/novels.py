from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.outbound.database.models.base_model import BaseModel


class CharacterModel(BaseModel):
    __tablename__ = "characters"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    arc: Mapped[str] = mapped_column(String, nullable=False)
    voice_notes: Mapped[str] = mapped_column(String, nullable=False)

    novel: Mapped["NovelModel"] = relationship(
        "NovelModel", back_populates="characters"
    )

    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel", back_populates="character", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<CharacterModel(id={self.id}, name={self.name}, novel_id={self.novel_id})>"


class RoadmapModel(BaseModel):
    __tablename__ = "roadmap"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id"), nullable=False
    )
    step_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str] = mapped_column(String, nullable=False)
    target_choice: Mapped[bool] = mapped_column(Boolean)
    choice_stakes: Mapped[str | None] = mapped_column(String)

    novel: Mapped["NovelModel"] = relationship("NovelModel", back_populates="roadmap")

    scenes: Mapped[list["SceneModel"]] = relationship(
        "SceneModel",
        back_populates="roadmap",
        cascade="all, delete-orphan",
        order_by="SceneModel.order",
    )

    def __repr__(self):
        return f"<RoadmapModel(id={self.id}, step_id={self.step_id}, novel_id={self.novel_id})>"


class NovelModel(BaseModel):
    __tablename__ = "novels"

    title: Mapped[str] = mapped_column(String, nullable=False)
    public_description: Mapped[str] = mapped_column(String, nullable=False)

    description: Mapped[str] = mapped_column(String, nullable=False)
    tone: Mapped[str] = mapped_column(String, nullable=False)

    characters: Mapped[list["CharacterModel"]] = relationship(
        "CharacterModel", back_populates="novel", cascade="all, delete-orphan"
    )
    roadmap: Mapped[list["RoadmapModel"]] = relationship(
        "RoadmapModel",
        back_populates="novel",
        cascade="all, delete-orphan",
        order_by="RoadmapModel.step_id",
    )
    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel", back_populates="novel", cascade="all, delete-orphan"
    )


class SceneModel(BaseModel):
    __tablename__ = "scenes"

    roadmap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roadmap.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    roadmap: Mapped["RoadmapModel"] = relationship(
        "RoadmapModel", back_populates="scenes"
    )

    dialogue_lines: Mapped[list["DialogueLineModel"]] = relationship(
        "DialogueLineModel",
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="DialogueLineModel.order",
    )

    def __repr__(self):
        return f"<SceneModel(id={self.id}, roadmap_id={self.roadmap_id}, order={self.order})>"


class DialogueLineModel(BaseModel):
    __tablename__ = "dialogue_lines"

    novel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("novels.id"), nullable=False, index=True
    )
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id"), nullable=False, index=True
    )
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id"), nullable=False, index=True
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String, nullable=False)
    is_final_for_roadmap: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    novel: Mapped["NovelModel"] = relationship(
        "NovelModel", back_populates="dialogue_lines"
    )
    scene: Mapped["SceneModel"] = relationship(
        "SceneModel", back_populates="dialogue_lines"
    )
    character: Mapped["CharacterModel"] = relationship(
        "CharacterModel", back_populates="dialogue_lines"
    )

    actions: Mapped[list["DialogueActionModel"]] = relationship(
        "DialogueActionModel",
        back_populates="dialogue_line",
        cascade="all, delete-orphan",
        order_by="DialogueActionModel.order",
    )

    def __repr__(self):
        return f"<DialogueLineModel(id={self.id}, scene_id={self.scene_id}, character_id={self.character_id})>"


class DialogueActionModel(BaseModel):
    __tablename__ = "dialogue_actions"

    dialogue_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dialogue_lines.id"), nullable=False, index=True
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(String, nullable=False)
    next_roadmap_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roadmap.id"), nullable=True
    )

    dialogue_line: Mapped["DialogueLineModel"] = relationship(
        "DialogueLineModel", back_populates="actions"
    )
    next_roadmap: Mapped["RoadmapModel" | None] = relationship(
        "RoadmapModel", foreign_keys=[next_roadmap_id]
    )

    def __repr__(self):
        return f"<DialogueActionModel(id={self.id}, dialogue_line_id={self.dialogue_line_id})>"

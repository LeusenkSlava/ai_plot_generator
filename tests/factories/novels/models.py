from datetime import datetime

from src.core.novels.models import Character, DialogueLine, Novel, Roadmap, Scene


def novel_character_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    novel_id: int = 1,
    name: str = "Алиса",
    role: str = "Ведьма",
    arc: str = "Найти пропавшего брата",
    voice_notes: str = "Говорит тихо",
    codex_character_id: int | None = None,
) -> Character:
    return Character(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        novel_id=novel_id,
        name=name,
        role=role,
        arc=arc,
        voice_notes=voice_notes,
        codex_character_id=codex_character_id,
    )


def novel_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    title: str = "Тень над лесом",
    public_description: str = "Ведьма ищет пропавшего брата.",
    description: str = "Полное описание сюжета...",
    tone: str = "dark",
    universe_id: int | None = None,
) -> Novel:
    return Novel(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        title=title,
        public_description=public_description,
        description=description,
        tone=tone,
        universe_id=universe_id,
    )


def valid_novel_llm_payload(
    *,
    title: str = "Тень над лесом",
    public_description: str = "Ведьма ищет пропавшего брата.",
    description: str = "Полное описание сюжета...",
    tone: str = "dark",
) -> dict:
    return {
        "title": title,
        "public_description": public_description,
        "description": description,
        "tone": tone,
    }


def roadmap_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    novel_id: int = 1,
    step_id: int = 1,
    title: str = "Шаг 1",
    goal: str = "Цель шага",
    target_choice: bool = False,
    choice_stakes: str | None = None,
    scenes_count: int = 2,
) -> Roadmap:
    return Roadmap(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        novel_id=novel_id,
        step_id=step_id,
        title=title,
        goal=goal,
        target_choice=target_choice,
        choice_stakes=choice_stakes,
        scenes_count=scenes_count,
    )


def scene_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    roadmap_id: int = 1,
    title: str = "Сцена",
    description: str = "Описание сцены",
    order: int = 1,
    is_final_for_roadmap: bool = False,
    is_final_for_novel: bool = False,
    story_context: str | None = None,
) -> Scene:
    return Scene(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        roadmap_id=roadmap_id,
        title=title,
        description=description,
        order=order,
        is_final_for_roadmap=is_final_for_roadmap,
        is_final_for_novel=is_final_for_novel,
        story_context=story_context,
    )


def dialogue_line_domain(
    *,
    id: int | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    novel_id: int = 1,
    scene_id: int = 1,
    character_id: int = 1,
    order: int = 1,
    text: str = "Реплика",
    is_final_for_scene: bool = False,
    background_asset_key: str | None = None,
    sprite_asset_key: str | None = None,
    outfit_asset_key: str | None = None,
    emotion_asset_key: str | None = None,
) -> DialogueLine:
    return DialogueLine(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        novel_id=novel_id,
        scene_id=scene_id,
        character_id=character_id,
        order=order,
        text=text,
        is_final_for_scene=is_final_for_scene,
        background_asset_key=background_asset_key,
        sprite_asset_key=sprite_asset_key,
        outfit_asset_key=outfit_asset_key,
        emotion_asset_key=emotion_asset_key,
    )


def dialogue_line_payload(
    *,
    character_name: str = "Алиса",
    text: str = "Реплика",
    **asset_fields,
) -> dict:
    """Одна реплика в ответе LLM. asset_fields — необязательные
    background_slug/sprite_slug/outfit_tag/emotion_base_tag/emotion_modifier_tags."""
    return {"character_name": character_name, "text": text, **asset_fields}


def valid_dialogue_llm_payload(*lines: dict) -> dict:
    """Валидный ответ LLM генератора диалога: список реплик."""
    return {"dialogue_lines": list(lines)}

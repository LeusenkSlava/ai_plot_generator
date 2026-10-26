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
    is_protagonist: bool = False,
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
        is_protagonist=is_protagonist,
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
    event: str = "Событие шага",
    conflict: str = "Конфликт шага",
    change: str = "Изменение шага",
    target_choice: bool = False,
    choice_stakes: str | None = None,
    scenes_count: int = 2,
    location_slug: str | None = None,
    time_of_day: str | None = None,
    day: int | None = None,
) -> Roadmap:
    return Roadmap(
        id=id,
        created_at=created_at,
        updated_at=updated_at,
        novel_id=novel_id,
        step_id=step_id,
        title=title,
        event=event,
        conflict=conflict,
        change=change,
        target_choice=target_choice,
        choice_stakes=choice_stakes,
        scenes_count=scenes_count,
        location_slug=location_slug,
        time_of_day=time_of_day,
        day=day,
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
    character_ids: list[int] | None = None,
    location_slug: str | None = None,
    time_of_day: str | None = None,
    day: int | None = None,
    needs_review: bool = False,
    review_reason: str | None = None,
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
        character_ids=character_ids if character_ids is not None else [],
        location_slug=location_slug,
        time_of_day=time_of_day,
        day=day,
        needs_review=needs_review,
        review_reason=review_reason,
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
    is_thought: bool = False,
    background_asset_key: str | None = None,
    sound_asset_key: str | None = None,
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
        is_thought=is_thought,
        background_asset_key=background_asset_key,
        sound_asset_key=sound_asset_key,
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
    background_base_tag/background_modifier_tags/outfit_tag/
    emotion_base_tag/emotion_modifier_tags."""
    return {"character_name": character_name, "text": text, **asset_fields}


def valid_dialogue_llm_payload(*lines: dict) -> dict:
    """Валидный ответ LLM генератора диалога: список реплик."""
    return {"dialogue_lines": list(lines)}

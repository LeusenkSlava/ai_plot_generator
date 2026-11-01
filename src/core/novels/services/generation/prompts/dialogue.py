"""Сборка промпта диалога — единственный источник его текста.

``DialoguePromptBuilder`` — чистая сборка сообщений LLM из шаблона и контекста
сцены: без БД и без вызова LLM. Раньше эта логика жила приватным
``DialogueGenerator.__create_prompt``, а скрипт ``regen_dialogue.py`` зеркалил её
вручную — два источника неизбежно разъезжались. Теперь прод и инструмент
собирают промпт одним кодом: генератор передаёт ``DialoguePromptContext``,
заполненный из БД/Codex, инструмент — тот же контекст с ``assets=None``.
"""

from dataclasses import dataclass

from src.core.novels.models import (
    Character,
    DialogueLine,
    LineKind,
    Prompt,
    Roadmap,
    Scene,
)
from src.core.novels.services.generation.assets import (
    SceneAssetService,
    SceneAssets,
    _short,
)
from src.core.novels.services.generation.prompts.cast import render_cast
from src.core.novels.services.generation.prompts.catalog import render_messages
from src.core.novels.services.generation.prompts.context import render_place_time
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE

PREVIOUS_LINE_MAX_CHARS = 300


@dataclass(frozen=True, slots=True)
class DialoguePromptContext:
    """Всё, что нужно для сборки промпта диалога, кроме самого шаблона.

    ``assets``/``current_outfits`` заполняет прод (после Codex-фазы); инструмент
    передаёт ``assets=None`` и ``current_outfits=""`` — текст он тестирует без
    визуала, asset-блоки при этом становятся пустыми.
    """

    scene: Scene
    roadmap: Roadmap
    characters: list[Character]  # участники сцены
    all_characters: list[Character]  # весь каст
    protagonist: Character | None
    assets: SceneAssets | None
    previous_lines: list[DialogueLine]
    story_context: str | None
    current_outfits: str
    used_phrases: list[str]
    previous_scene: Scene | None


def _choice_hint(roadmap: Roadmap) -> str:
    """Подсказка о выборе: шаг с target_choice должен подвести диалог к решению.

    Сами варианты выбора не пишем — они уже зафиксированы на шаге роадмапа
    (roadmap_choices) и раздаются через playback.
    """
    if not roadmap.target_choice:
        return "The story is linear: do not offer the player any choices.\n"
    stakes = roadmap.choice_stakes or "the protagonist's decision"
    return (
        "This scene ends with a player choice. The choice is about: "
        f"{stakes}. Lead the dialogue to the moment of decision — the final line "
        "should naturally set up the choice — but do NOT write the choice options "
        "themselves; they are provided separately.\n"
    )


class DialoguePromptBuilder:
    """Собирает сообщения LLM из шаблона диалога и контекста сцены."""

    def __init__(self, scene_assets: SceneAssetService | None = None):
        # Нужен только для ``assets_catalog``, который рендерится при ``ctx.assets``.
        # Инструмент, тестирующий текст без визуала, передаёт ``None`` (и ``assets=None``).
        self._scene_assets = scene_assets

    def build(self, template: Prompt, ctx: DialoguePromptContext) -> list[dict]:
        # Полный каст в фиксированном порядке — стабильная голова промпта для кэша.
        cast = render_cast(ctx.all_characters)
        scene_participants = ", ".join(c.name for c in ctx.characters)

        protagonist_block = ""
        if ctx.protagonist:
            protagonist_block = (
                f"\nThe protagonist is {ctx.protagonist.name}. The story is told from their point of view, "
                "so build the dialogue around their perception, goals, and decisions. "
                "They have no sprite or emotions on screen: for their lines do not specify an outfit or emotions. "
                'Their lines can be speech out loud (kind="speech") or inner thoughts '
                '(kind="thought") — use inner thoughts to convey their feelings and motives.'
            )

        asset_catalog = ""
        assets_block = ""
        if ctx.assets:
            if self._scene_assets is None:
                raise ValueError(
                    "DialoguePromptBuilder: scene_assets is required when assets are present"
                )
            assets_block = (
                "\nFor the visual of each line, pick assets ONLY from the catalog, "
                "specifying slugs and tags exactly as in the catalog, and add these fields to the line object:\n"
                "- background_base_tag - ONE location tag from the location list that fits the scene's place "
                "(usually one for the whole scene; change it only if the action moves to another place);\n"
                "- background_modifier_tags - a list of 0 or more modifier tags from the modifier list "
                "(time of day, inside/outside, light, people) matching the scene's time and setting;\n"
                "- outfit_tag - ONE outfit style tag from the speaker's outfits;\n"
                "- emotion_base_tag - ONE main emotion tag from the base emotions of the chosen outfit, "
                "matching the text of the line;\n"
                "- emotion_modifier_tags - a list of 0 or more emotion modifier tags "
                "from the modifiers of the chosen outfit.\n"
                "Pick the outfit first, then choose the emotions ONLY from the emotions "
                "listed under that chosen outfit.\n"
                "For the protagonist's lines (no sprite), set null for outfit_tag and "
                "emotion_base_tag and an empty list [] for emotion_modifier_tags; "
                "specify the background (background_base_tag and background_modifier_tags) as for other lines.\n"
                "For narration lines (kind=\"narration\"), there is no sprite, outfit, or emotion: "
                "set null for outfit_tag and emotion_base_tag and an empty list [] for "
                "emotion_modifier_tags; specify only the background "
                "(background_base_tag and background_modifier_tags) as for other lines.\n"
                "If there is no suitable asset, set null; for emotion_modifier_tags set an empty list [].\n"
                "A character's outfit does not change between lines and scenes: keep using their current "
                "outfit_tag until the plot clearly has them change clothes."
            )
            asset_catalog = "\n\nAsset catalog:\n" + self._scene_assets.assets_catalog(
                ctx.all_characters, ctx.assets
            )

        story_context_block = ""
        if ctx.story_context:
            story_context_block = (
                "\n\nStory so far (do not contradict it; "
                "characters are dressed as stated there until the plot has them change clothes):\n"
                f"{ctx.story_context}"
            )

        current_outfits_block = ""
        if ctx.current_outfits:
            current_outfits_block = f"\n\nCurrent character outfits:\n{ctx.current_outfits}"

        previous_scene_block = ""
        if ctx.previous_scene is not None:
            previous_scene_block = (
                "\n\nPrevious scene (where the story left off): "
                f"{ctx.previous_scene.title} — "
                f"{render_place_time(ctx.previous_scene.location_slug, ctx.previous_scene.time_of_day, ctx.previous_scene.day)}."
            )

        previous_lines_block = ""
        if ctx.previous_lines:
            names = {character.id: character.name for character in ctx.all_characters}
            recap = "\n".join(
                self.render_previous_line(line, names) for line in ctx.previous_lines
            )
            previous_lines_block = (
                "\n\nLast lines of the previous scene (continue the story, do not repeat them):\n"
                f"{recap}"
            )

        used_phrases_block = ""
        if ctx.used_phrases:
            used_phrases_block = (
                "\n\nPhrases already used in the story (do not repeat them verbatim):\n"
                + "\n".join(f"- {p}" for p in ctx.used_phrases)
            )

        return render_messages(
            template,
            system_vars={
                "choice_hint": _choice_hint(ctx.roadmap),
                "protagonist_block": protagonist_block,
                "assets_block": assets_block,
                "russian_note": RUSSIAN_OUTPUT_NOTE,
            },
            user_vars={
                "cast": cast,
                "asset_catalog": asset_catalog,
                "story_context_block": story_context_block,
                "current_outfits_block": current_outfits_block,
                "previous_scene_block": previous_scene_block,
                "previous_lines_block": previous_lines_block,
                "used_phrases_block": used_phrases_block,
                "scene_title": ctx.scene.title,
                "scene_description": ctx.scene.description,
                "place_time": render_place_time(
                    ctx.scene.location_slug, ctx.scene.time_of_day, ctx.scene.day
                ),
                "scene_participants": scene_participants,
            },
        )

    @staticmethod
    def render_previous_line(
        line: DialogueLine,
        names: dict[int | None, str],
        narration_label: str = "[narration]",
    ) -> str:
        """Одна прошлая реплика для блока «последние реплики».

        ``narration_label`` задаётся вызывающим: в промпте диалога — ``[narration]``,
        в изложении истории — ``[описание]``.
        """
        text = _short(line.text, PREVIOUS_LINE_MAX_CHARS)
        if line.kind is LineKind.NARRATION:
            return f"{narration_label} {text}"
        name = names.get(line.character_id, "?")
        thought = " (thoughts)" if line.kind is LineKind.THOUGHT else ""
        return f"{name}{thought}: {text}"

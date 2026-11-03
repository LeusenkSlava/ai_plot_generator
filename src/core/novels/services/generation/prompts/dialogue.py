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
    SceneAssets,
    SceneAssetService,
    _short,
)
from src.core.novels.services.generation.prompts.cast import render_cast
from src.core.novels.services.generation.prompts.catalog import render_messages
from src.core.novels.services.generation.prompts.context import render_place_time
from src.core.novels.services.generation.prompts.text import RUSSIAN_OUTPUT_NOTE

PREVIOUS_LINE_MAX_CHARS = 300

OUTFIT_POLICY = (
    "An outfit is chosen for the scene, not fixed for the whole novel. Within one scene a "
    "character keeps one outfit_tag unless the narration explicitly shows them changing clothes; "
    "a new outfit must be introduced by narration, never appear suddenly on a later line. "
    "Between scenes the outfit may change when the scene's place, time or event gives a concrete "
    "reason: a beach, bathhouse or pool (especially a night party or a swim), sport, a cold night "
    "outside, sleep, a formal event. If the scene description does not name the clothes, choose "
    "them from the place, time and event rather than from the previous scene. Do not carry the "
    "previous outfit by inertia: at a night beach party the natural outfit is swimwear, not the "
    "camp uniform. If you change an outfit relative to «Current character outfits», the first "
    "narration beat with that character must show the new clothes — what they are wearing and, "
    "if it matters, how they changed; a dialogue line alone cannot carry a change of clothes. "
    "If the scene gives no such reason, keep the current outfit_tag."
)

CURRENT_OUTFITS_HEADER = (
    "\n\nCurrent character outfits (from their last appearance; this scene may start with other "
    "clothes — if you change them, show it in narration):\n"
)


@dataclass(frozen=True, slots=True)
class DialoguePromptContext:
    """Контекст для сборки промпта диалога (всё, кроме шаблона).

    ``assets``/``current_outfits`` заполняет прод; инструмент тестирует текст
    без визуала и передаёт ``assets=None``, ``current_outfits=""``.
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
    # Позиция сцены в шаге роадмапа (1..N), чтобы шаг раскладывался по сценам целиком.
    scene_position: int = 0
    scenes_count: int = 0


def _choice_hint(roadmap: Roadmap) -> str:
    """Подсказка о выборе: подводит диалог к решению.

    Варианты не пишем — они уже есть в roadmap_choices и раздаются через playback.
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
        # Только для assets_catalog; без визуала инструмент передаёт None.
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
                'For narration lines (kind="narration"), there is no sprite, outfit, or emotion: '
                "set null for outfit_tag and emotion_base_tag and an empty list [] for "
                "emotion_modifier_tags; specify only the background "
                "(background_base_tag and background_modifier_tags) as for other lines.\n"
                "If there is no suitable asset, set null; for emotion_modifier_tags set an empty list [].\n"
            ) + OUTFIT_POLICY
            asset_catalog = "\n\nAsset catalog:\n" + self._scene_assets.assets_catalog(
                ctx.all_characters, ctx.assets
            )

        story_context_block = ""
        if ctx.story_context:
            story_context_block = (
                "\n\nStory so far (do not contradict it; "
                "characters keep the clothes described there unless this scene shows them changing):\n"
                f"{ctx.story_context}"
            )

        current_outfits_block = ""
        if ctx.current_outfits:
            current_outfits_block = CURRENT_OUTFITS_HEADER + ctx.current_outfits

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

        # Диалог пишется и по биту шага роадмапа; иначе шаг обрывался на подходе (см. nsfw_high v2/v3).
        step_block = "\n".join(
            (
                f"Roadmap step: {ctx.roadmap.title}",
                f"Step event: {ctx.roadmap.event}",
                f"Step conflict: {ctx.roadmap.conflict}",
                f"Step change: {ctx.roadmap.change}",
            )
        )
        if ctx.scenes_count:
            step_block += (
                f"\nScene {ctx.scene_position} of {ctx.scenes_count} within the step."
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
                "step_block": step_block,
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

        ``narration_label`` — ``[narration]`` в диалоге, ``[описание]`` в изложении.
        """
        text = _short(line.text, PREVIOUS_LINE_MAX_CHARS)
        if line.kind is LineKind.NARRATION:
            return f"{narration_label} {text}"
        name = names.get(line.character_id, "?")
        thought = " (thoughts)" if line.kind is LineKind.THOUGHT else ""
        return f"{name}{thought}: {text}"

"""Библиотека нарративных форм истории: биты по порядку и заметки по раскладке.

Тексты уходят в промпты ``plot_design`` (каталог форм) и ``roadmap`` (полное
описание выбранной формы), поэтому источник правды здесь, в коде, а не в БД.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ShapeBeat:
    """Один бит формы: имя-метка и что в нём должно произойти."""

    name: str
    description: str


@dataclass(frozen=True)
class StoryShape:
    """Нарративная форма: биты по порядку и три заметки по раскладке."""

    slug: str
    title: str
    beats: list[ShapeBeat]
    # раскладка битов по шагам роадмапа
    step_note: str
    # распределение конфликтных и тихих/интимных битов
    conflict_note: str
    # где в этой форме ложатся эротические биты (только для 18+ вариантов)
    heat_note: str = ""
    # форма доступна только взрослым вариантам; в default она не попадает в каталог
    adult_only: bool = False


STORY_SHAPES: dict[str, StoryShape] = {
    "hero_cycle": StoryShape(
        slug="hero_cycle",
        title="Hero's journey — quest/search/mystery",
        beats=[
            ShapeBeat(
                "Ordinary world",
                "the hero in ordinary life; convey a dissatisfaction or a desire so there "
                "is a reason to change.",
            ),
            ShapeBeat(
                "Need",
                "the hero's concrete goal/desire that sets the direction of the whole "
                "story; a through-line that must not be dropped before the finale.",
            ),
            ShapeBeat(
                "Go",
                "an event knocks the hero out of ordinary life into an unfamiliar "
                "situation (the inciting incident).",
            ),
            ShapeBeat(
                "Search",
                "the hero tries to reach the goal, hits obstacles, forms relationships; "
                "around the middle a turn changes the stakes.",
            ),
            ShapeBeat(
                "Find",
                "the hero gets what they wanted, but in an unexpected or imperfect form.",
            ),
            ShapeBeat(
                "Take",
                "the find has to be paid for: a loss, a conflict, a consequence; a real "
                "threat of failure before the climax.",
            ),
            ShapeBeat(
                "Return",
                "the hero comes back to a familiar situation, but changed; the key event "
                "(a confession, a decision, an act) plays out here.",
            ),
            ShapeBeat(
                "Change",
                "the final state of the hero/world and the takeaway of the story; a "
                "resolution, not a cliffhanger.",
            ),
        ],
        step_note=(
            "8 beats → 8–12 steps; the first and last usually take one step each, "
            "beats 4–6 may stretch over 2 steps."
        ),
        conflict_note="most steps carry a real conflict; the final step resolves.",
        heat_note=(
            "erotic beats fit the Search/Find/Take beats (the middle), escalating "
            "toward the Take; do not front-load them or reserve them all for the Return."
        ),
    ),
    "relationship_arc": StoryShape(
        slug="relationship_arc",
        title="Relationship arc — romance/erotica",
        beats=[
            ShapeBeat(
                "Encounter",
                "the first meeting/hook: who, where and why they start interacting; by "
                "the end of the step the hero has a reason to see this person again.",
            ),
            ShapeBeat(
                "Attraction",
                "interest and pull while distance remains: what attracts and what "
                "prevents getting closer.",
            ),
            ShapeBeat(
                "Deepening",
                "growing closer through a shared task, a conversation, vulnerability; the "
                "first shift in the relationship.",
            ),
            ShapeBeat(
                "Complication",
                "an outside or inside complication: jealousy, rules, fear, an obligation.",
            ),
            ShapeBeat(
                "Rupture",
                "a break/pullback: a conflict, a misunderstanding or a separation puts "
                "the relationship in question.",
            ),
            ShapeBeat(
                "Repair",
                "reconciliation: a confession, a choice, an act that shows change.",
            ),
            ShapeBeat(
                "Commitment",
                "the new reality of the relationship, an outcome rather than a cliffhanger.",
            ),
        ],
        step_note="7 beats → 7–11 steps; beats 4–5 may stretch over 2 steps.",
        conflict_note=(
            "early beats (1–3) may be quiet/intimate (empty conflict); beats 4–5 carry "
            "the real conflict; beats 6–7 resolve."
        ),
        heat_note=(
            "erotic beats live in Attraction/Deepening and peak in Commitment; the "
            "first intimate beat must land by the Deepening beat, not only in Commitment."
        ),
    ),
    "slice_of_life": StoryShape(
        slug="slice_of_life",
        title="Slice of life — episodes around a theme, no crisis",
        beats=[
            ShapeBeat(
                "Setup",
                "ordinary life and the familiar world; a mild dissatisfaction or a theme.",
            ),
            ShapeBeat(
                "Episodes",
                "free middle, 2–6 steps: episodes around the theme, each step its own "
                "situation/nuance, not a repeat of the previous one; conflict is "
                "optional, texture and a shift matter.",
            ),
            ShapeBeat(
                "Turn",
                "a quiet shift of perception: the hero sees something in a new way.",
            ),
            ShapeBeat(
                "Reflection",
                "the final picture, a takeaway without moralizing.",
            ),
        ],
        step_note=(
            "no fixed number of beats; 6–10 steps; anchors only at the start and the "
            "end, the middle is free episodes."
        ),
        conflict_note=(
            "most steps are quiet/textural (empty conflict); one or two carry light "
            "friction."
        ),
        heat_note=(
            "each episode may carry its own heat; spread the intimate episodes across "
            "the middle so heat appears from early on, not only in the last episode."
        ),
    ),
    "mystery_unfolding": StoryShape(
        slug="mystery_unfolding",
        title="Unfolding mystery — detective/suspense",
        beats=[
            ShapeBeat(
                "Incident",
                "an incident/mystery: something happens that cannot be left unanswered.",
            ),
            ShapeBeat(
                "Hook",
                "the stake: why the hero is obliged to get involved.",
            ),
            ShapeBeat(
                "Investigation",
                "investigation: clues, witnesses, connections.",
            ),
            ShapeBeat(
                "False lead",
                "a false lead/turn: what looked like the answer was not.",
            ),
            ShapeBeat(
                "Twist",
                "the revelation/twist: a truth that changes the picture.",
            ),
            ShapeBeat(
                "Aftermath",
                "the consequences and the outcome.",
            ),
        ],
        step_note=(
            "6 beats → 8–12 steps; the investigation and the false lead may each "
            "stretch over 2 steps."
        ),
        conflict_note="every step carries a risk or a question; the final step resolves.",
        heat_note=(
            "heat is optional color; if present, place it on Investigation/False-lead "
            "steps so it does not wait for the Aftermath."
        ),
    ),
    "farce": StoryShape(
        slug="farce",
        title="Farce — escalating misunderstandings in a short time",
        beats=[
            ShapeBeat(
                "Setup",
                "the premise: a misunderstanding/secret/stake everything grows from.",
            ),
            ShapeBeat(
                "Escalation",
                "escalation: attempts to get out only make things worse; the absurdity "
                "grows.",
            ),
            ShapeBeat(
                "Peak",
                "the peak of confusion: everything converges in one point.",
            ),
            ShapeBeat(
                "Unravel",
                "untying the knots: the truth comes out.",
            ),
            ShapeBeat(
                "Payoff",
                "the resolution and the outcome.",
            ),
        ],
        step_note="5 beats → 6–10 steps; the escalation may stretch over 2–3 steps.",
        conflict_note=(
            "the conflict is comic and growing, not tragic; the finale resolves it."
        ),
        heat_note=(
            "heat rides the Escalation/Peak steps — the misunderstanding creates erotic "
            "situations; put the first such beat early in the Escalation."
        ),
    ),
    "rivalry": StoryShape(
        slug="rivalry",
        title="Rivalry — love triangle/competition",
        beats=[
            ShapeBeat(
                "Arrival",
                "the arrival of a rival/competitor: the stakes are sketched.",
            ),
            ShapeBeat(
                "Bids",
                "both sides push for their goal: parallel attempts.",
            ),
            ShapeBeat(
                "Tipping",
                "the scales tip: the advantage changes hands.",
            ),
            ShapeBeat(
                "Choice",
                "the choice/stake: the hero has to decide.",
            ),
            ShapeBeat(
                "Consequence",
                "the price of the choice: a loss or a consequence.",
            ),
            ShapeBeat(
                "Settlement",
                "the outcome and the new arrangement.",
            ),
        ],
        step_note="6 beats → 7–11 steps; bids/tipping may stretch.",
        conflict_note=(
            "the conflict lives in comparison and choice; the final step settles it."
        ),
        heat_note=(
            "heat lives in the Bids/Tipping steps (both sides pursue); do not reserve "
            "it for the Settlement."
        ),
    ),
    "erotic_escalation": StoryShape(
        slug="erotic_escalation",
        title="Erotic escalation — discovery/exposure ladder (adult only)",
        beats=[
            ShapeBeat(
                "First exposure",
                "the protagonist's trait or premise is exposed or noticed for the "
                "first time (a caught look, a seen moment); the erotic engine starts "
                "here, on step 1 or 2.",
            ),
            ShapeBeat(
                "Witnesses",
                "the news spreads or others seek to see it (gossip, peeking, a second "
                "exposure); each witness is a concrete erotic beat, not a mere mention.",
            ),
            ShapeBeat(
                "Escalation",
                "a chain of concrete encounters, each more explicit than the previous "
                "one (the first touch, the first act); each step is its own situation, "
                "partner or act.",
            ),
            ShapeBeat(
                "Peak",
                "the most explicit encounter — the act the story has been building "
                "toward.",
            ),
            ShapeBeat(
                "Aftermath",
                "the consequences of the peak: what changes between the characters; a "
                "resolution, not a cliffhanger.",
            ),
        ],
        step_note=(
            "6–10 steps; the first exposure takes step 1–2, escalations may each take "
            "a step, the peak lands one step before the end so the aftermath closes "
            "the story."
        ),
        conflict_note=(
            "the conflict is the tension around exposure (being caught, gossip, "
            "rivalry), never an obstacle that postpones the act."
        ),
        heat_note=(
            "explicit beats start with the first exposure and escalate on every "
            "escalation step; the first act must land no later than the second "
            "escalation, and the peak is the penultimate step."
        ),
        adult_only=True,
    ),
}

DEFAULT_SHAPE = "hero_cycle"


def get_shape(slug: str) -> StoryShape:
    """Форма по slug; неизвестный или пустой slug — форма по умолчанию."""
    return STORY_SHAPES.get((slug or "").strip().lower(), STORY_SHAPES[DEFAULT_SHAPE])


def render_shape_catalog(adult: bool = False) -> str:
    """Каталог форм для промпта ``plot_design`` (``- slug: title``).

    Для обычных вариантов формы с ``adult_only=True`` скрываются.
    """
    shapes = [
        shape
        for shape in STORY_SHAPES.values()
        if adult or not shape.adult_only
    ]
    return "\n".join(f"- {shape.slug}: {shape.title}" for shape in shapes)


def render_shape_block(slug: str, adult: bool = False) -> str:
    """Полное описание формы для промпта ``roadmap``: биты по порядку и заметки."""
    shape = get_shape(slug)
    lines = [f"Shape: {shape.title}", "Beats (follow in this order):"]
    for index, beat in enumerate(shape.beats, start=1):
        lines.append(f"{index}. {beat.name} — {beat.description}")
    lines.append(f"How to spread the beats across steps: {shape.step_note}")
    lines.append(f"Conflict distribution: {shape.conflict_note}")
    if adult and shape.heat_note:
        lines.append(f"Heat distribution: {shape.heat_note}")
    return "\n".join(lines)

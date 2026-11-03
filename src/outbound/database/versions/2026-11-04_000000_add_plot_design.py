"""Design-doc (форма истории + нити + бюджет) перед роадмапом

Revision ID: e3b7c1d9a2f4
Revises: d1e2f3a4b5c6
Create Date: 2026-11-04 00:00:00.000000

Публикует шаг ``plot_design`` (version 1) и roadmap с формой истории и
design-doc для вариантов ``default``, ``nsfw_low``, ``nsfw_medium``,
``nsfw_high``. ``nsfw_extra`` (чистый секс без драматургии) и устаревший
``nsfw`` не меняются.

Для ``nsfw_high`` roadmap переписан целиком (version 2); для остальных —
новая версия на базе их текущего текста: круг Хармана вырезан, правила
design-doc вставлены перед JSON-схемой, heat-блоки low/medium сохранены.
Базовый текст читается из фиксированной версии, поэтому повторный запуск
миграции даёт тот же результат.

Схема: ``roadmap.beat_type`` и ``novels.plot_design`` (JSONB-снапшот).
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3b7c1d9a2f4'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PLOT_DESIGN_VERSION = 1

# вариант -> (версия roadmap с исходным текстом, публикуемая версия)
_ROADMAP_VERSIONS: dict[str, tuple[int, int]] = {
    "default": (2, 3),
    "nsfw_low": (1, 2),
    "nsfw_medium": (1, 2),
    "nsfw_high": (1, 2),
}
_ROADMAP_FULL_REWRITE = "nsfw_high"


_PLOT_DESIGN_BODY = """Based on the story description, its tone and the cast, produce a compact design brief that will steer the plot roadmap. Your job is NOT to write scenes — it is to choose the story's structural shape, name the plot threads, and give them a budget so the story does not collapse into a single repeated idea.

Choose the shape from the catalog below (by slug) that best fits the story's genre, tone and scale:
{shape_catalog}

Then, for the story, specify:
1. shape - the slug of the chosen shape, exactly from the catalog.
2. genres - 1 to 4 short genre labels for this story (e.g. "romcom", "erotica", "drama", "mystery").
3. through_line - ONE sentence: what the whole story is really about, on the level of the protagonist's desire, flaw or internal conflict. It must NOT be a restatement of a single fetish or a single event from the user's request; it names what changes for the protagonist across the arc.
4. threads - 3 to 5 distinct plot threads that the roadmap will interleave. Each thread is a different engine of the story (a relationship, a secret, a conflict, an obligation, a question). For each:
   - name - a short label for the thread;
   - characters - the names of the characters this thread runs through, ONLY from the cast (1 to 3 names);
   - min_steps - the minimum number of roadmap steps this thread must drive (integer >= 1);
   - max_steps - the maximum number of steps this thread may drive (integer, strictly greater than min_steps).
   The sum of min_steps must be close to the planned number of steps and must leave room for the other threads; no single thread may have min_steps above half the planned step count. If the user's request revolves around one specific kink or premise, that kink is ONE thread at most — the other threads must be distinct narrative engines (relationships, secrets, rules, rivalry, work, family), so the story is not a monotone repetition of the premise.
5. tropes - 2 to 6 narrative moves or tropes to weave in as ingredients (e.g. "secret_reveal", "gossip_spreads", "jealous_friend", "caught_in_the_act", "power_imbalance"). These are optional colors, not the plot: they may be used where they fit and skipped where they do not.
6. pivot - ONE sentence describing the mid-story turn that raises the stakes or re-frames the protagonist's goal (the moment the story stops being what it appeared to be). It must involve at least one character from the cast.
7. tone_curve - the intended emotional register of the steps in order, as 3 to 6 short labels (e.g. ["comedy", "tension", "intimacy", "drama", "resolve"]).

Answer STRICTLY as JSON matching this schema:
{
  "shape": string,
  "genres": [string],
  "threads": [
    {
      "name": string,
      "characters": [string],
      "min_steps": integer,
      "max_steps": integer
    }
  ],
  "through_line": string,
  "tropes": [string],
  "pivot": string,
  "tone_curve": [string]
}
"""

_PLOT_DESIGN_POLICY_ADULT = "Content policy: every character is an adult (18+). The design brief may plan intimate and erotic beats between consenting adults, but they must serve the through-line and be distributed across the threads, never the story's sole purpose. Never involve minors."

_PLOT_DESIGN_POLICY_NEUTRAL = "Content policy: every character is an adult (18+). The design brief plans relationships, tension and plot turns, not explicit scenes. Never involve minors."

_PLOT_DESIGN_USER = """Title: {title}
Description: {description}
Narrative tone: {tone}{characters_block}
User request: {user_prompt}"""


# Правила design-doc для roadmap: общие для всех вариантов.
_DESIGN_RULES = """Follow the story shape given in the user message. Its beats are a guide to the ORDER and PURPOSE of the steps: do not skip the first and last beats, and do not reorder the beats. Spread the beats across steps as the shape's guidance says. The beats are a skeleton, not a formula: the content of each step comes from the threads, the characters and the through-line, and every step must be a concrete situation, not an abstract label.

The design brief also gives you a thread budget. Treat it as a hard constraint:
- Each thread must drive at least its min_steps steps and no more than its max_steps steps.
- A step may advance one or two threads, but every step must clearly serve at least one thread.
- Do not let one thread (especially the user's stated kink or premise) swallow the others: distribute the steps across all threads so the story has several interleaved engines.
- The through_line names what the story is really about; make each step's change move the protagonist along that through_line, and do not drop it before the final step.
- The pivot is the mid-story turn: place it roughly in the middle of the roadmap and make it re-frame the stakes.
- The tropes are optional ingredients: weave in the ones that fit this story and skip the rest; never build a step only to showcase a trope."""

# Вариантам без переписанного шаблона beat_type описывается отдельным абзацем.
_BEAT_TYPE_RULES = """For every step also specify beat_type - the kind of this step, one of: "setup" (establishing a character, place or premise), "escalation" (the stakes or intimacy grow), "intimacy" (a close/erotic beat), "texture" (a quiet scene that adds depth, no conflict), "obstacle" (an external or internal barrier), "reversal" (a turn that changes the stakes), "resolution" (a beat that resolves a thread or the story). Every story must contain at least one "obstacle" and one "reversal"; "texture" and "intimacy" steps must not outnumber the plot-moving steps."""

_HARMON_START = "The story structure is Harmon's story circle"
_HARMON_END = "Track when each significant character first enters the story."
_SCHEMA_ANCHOR = "Answer STRICTLY as JSON matching this schema:"


_ROADMAP_HEAD = """You are a professional author of adult (18+) visual novels. Based on the story description, its tone and the design brief below, create a plot roadmap — {story_shape} Decide the number of steps yourself based on the scale of the story — usually 8 to 12; the more steps, the richer the story, but each step must move the plot forward rather than repeat the previous one. For each step, specify:
1. title - a short title for the step.
2. event - ONE completed event/beat that happens in this step; do not stretch the step over a whole arc — it should fit into 1–2 scenes.
3. conflict - what makes this event hard for the protagonist: an obstacle, a contradiction, a risk, or what is at stake. Leave it as an empty string when the step is a quiet or intimate beat that moves the relationship or the theme forward without an obstacle — not every step needs a dramatized conflict.
4. change - what changes for the protagonist by the end of the step: a decision, a feeling, or a shift in a relationship; one concrete consequence.
5. beat_type - the kind of this step, one of: "setup" (establishing a character, place or premise), "escalation" (the stakes or intimacy grow), "intimacy" (a close/erotic beat), "texture" (a quiet scene that adds depth, no conflict), "obstacle" (an external or internal barrier), "reversal" (a turn that changes the stakes), "resolution" (a beat that resolves a thread or the story). Every story must contain at least one "obstacle" and one "reversal"; "texture" and "intimacy" steps must not outnumber the plot-moving steps.
6. scenes_count - 1 or 2 for a regular step; the final step and steps with a character's resolution may have 2 or 3. Use 2/3 only if each scene has its own beat, otherwise the scene will replay the previous one.
7. location_slug - the slug of the location where the step takes place, ONLY from the location list (empty string if there is no list).
8. time_of_day - the slug of the step's time of day, ONLY from the time-of-day list (empty string if there is no list).
9. day - the story day number: an integer from 1, non-decreasing between steps; if the step takes place on the same day as the previous one, use the same number."""

_ROADMAP_TAIL = """Track when each significant character first enters the story. The first time a significant character appears, dedicate a step to establishing the meeting: where and how the protagonist meets them and what makes them start interacting. Do not write a step whose event already assumes an established relationship (someone already teaching, helping, or being close to the protagonist) unless an earlier step introduced them and set up that interaction. Treat the story premise (a lesson, friendship, romance) as a goal to build toward across the arc, not as the starting state of its first related scene.
Spread the action across place and time: adjacent steps may stay in the same location when the story flows naturally there; change location when the plot requires it (a move, a new activity, a new beat), not for the sake of variety. Every scene within a step must match the step's place and day.
Build event/conflict/change only on the characters from the list below; do not mention in event, conflict, or change characters who are not in the list (even if they exist in the universe) — scenes with such characters will not pass validation and will be regenerated.
{choice_instructions}Answer STRICTLY as JSON matching this schema:
{schema}
Content policy: every character is an adult (18+); the story may include intimate and erotic beats between consenting adults. Such a beat still needs its own event, conflict and change and must move the plot forward — never let intimacy become the story's sole purpose.
{russian_note}"""

_ROADMAP_SYSTEM_HIGH = _ROADMAP_HEAD + "\n\n" + _DESIGN_RULES + "\n\n" + _ROADMAP_TAIL

_ROADMAP_USER = """User request: {user_prompt}

Title: {title}
Description: {description}
Narrative tone: {tone}

Story shape (follow its beats in order):
{shape_block}

Design brief (thread budget and through-line):
{design_block}{place_time_catalog}{characters_block}"""


def _plot_design_system(variant: str) -> str:
    """System-шаблон plot_design: для default политика без эротики."""
    adult = variant != "default"
    return (
        "You are a professional story designer for "
        + ("adult (18+) " if adult else "")
        + "visual novels. "
        + _PLOT_DESIGN_BODY
        + (_PLOT_DESIGN_POLICY_ADULT if adult else _PLOT_DESIGN_POLICY_NEUTRAL)
        + "\n{russian_note}"
    )


def _roadmap_system(bind: sa.Connection, variant: str) -> str:
    """System-шаблон roadmap: переписанный для high, иначе — база + design-doc."""
    if variant == _ROADMAP_FULL_REWRITE:
        return _ROADMAP_SYSTEM_HIGH
    base_version, _ = _ROADMAP_VERSIONS[variant]
    base = bind.execute(
        sa.text(
            "SELECT system_template FROM prompts "
            "WHERE key = 'roadmap' AND variant = :variant AND version = :version"
        ),
        {"variant": variant, "version": base_version},
    ).scalar_one()
    return _with_design(base)


def _with_design(system: str) -> str:
    """Вырезает круг Хармана и вставляет правила design-doc перед JSON-схемой."""
    start = system.find(_HARMON_START)
    end = system.find(_HARMON_END)
    if 0 <= start < end:
        system = system[:start] + system[end:]
    block = _BEAT_TYPE_RULES + "\n\n" + _DESIGN_RULES
    if _SCHEMA_ANCHOR in system:
        return system.replace(
            _SCHEMA_ANCHOR, "\n\n" + block + "\n\n" + _SCHEMA_ANCHOR, 1
        )
    return system + "\n\n" + block


def _publish(
    bind: sa.Connection,
    *,
    key: str,
    variant: str,
    version: int,
    system: str,
    user: str,
) -> None:
    """Публикует версию шаблона; повторный запуск обновляет текст (append-only)."""
    now = datetime.now(UTC)
    ids = {"key": key, "variant": variant, "version": version, "now": now}
    params = {**ids, "system": system, "user": user}
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM prompts "
            "WHERE key = :key AND variant = :variant AND version = :version"
        ),
        ids,
    ).scalar_one_or_none()
    if exists:
        bind.execute(
            sa.text(
                "UPDATE prompts SET system_template = :system, user_template = :user, "
                "updated_at = :now "
                "WHERE key = :key AND variant = :variant AND version = :version"
            ),
            params,
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO prompts "
                "(key, variant, version, system_template, user_template, is_active, "
                "created_at, updated_at) "
                "VALUES (:key, :variant, :version, :system, :user, false, :now, :now)"
            ),
            params,
        )
    # Активна ровно одна версия пары (key, variant) — публикуемая.
    bind.execute(
        sa.text(
            "UPDATE prompts SET is_active = false, updated_at = :now "
            "WHERE key = :key AND variant = :variant AND version <> :version"
        ),
        ids,
    )
    bind.execute(
        sa.text(
            "UPDATE prompts SET is_active = true, updated_at = :now "
            "WHERE key = :key AND variant = :variant AND version = :version"
        ),
        ids,
    )


def _assert_single_active(bind: sa.Connection, key: str, variant: str) -> None:
    """У пары (key, variant) ровно одна активная версия, иначе каталог сломается."""
    active = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM prompts "
            "WHERE key = :key AND variant = :variant AND is_active"
        ),
        {"key": key, "variant": variant},
    ).scalar_one()
    if active != 1:
        raise RuntimeError(
            f"{key}/{variant} prompts: expected 1 active row, got {active}"
        )


def upgrade() -> None:
    """Upgrade schema: колонки beat_type/plot_design и промпты всех вариантов."""
    op.add_column("roadmap", sa.Column("beat_type", sa.String(32), nullable=True))
    op.add_column(
        "novels",
        sa.Column(
            "plot_design", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    bind = op.get_bind()
    for variant, (_, version) in _ROADMAP_VERSIONS.items():
        _publish(
            bind,
            key="plot_design",
            variant=variant,
            version=_PLOT_DESIGN_VERSION,
            system=_plot_design_system(variant),
            user=_PLOT_DESIGN_USER,
        )
        _publish(
            bind,
            key="roadmap",
            variant=variant,
            version=version,
            system=_roadmap_system(bind, variant),
            user=_ROADMAP_USER,
        )
        for key in ("plot_design", "roadmap"):
            _assert_single_active(bind, key, variant)

    # DeepSeek при response_format=json_object отвечает 400, если в промпте нет
    # слова "json": проверяем на этапе миграции, а не в рантайме.
    for variant in _ROADMAP_VERSIONS:
        without_json = bind.execute(
            sa.text(
                "SELECT key FROM prompts WHERE variant = :variant AND is_active "
                "AND key IN ('plot_design', 'roadmap') "
                "AND LOWER(system_template) NOT LIKE '%json%' ORDER BY key"
            ),
            {"variant": variant},
        ).scalars().all()
        if without_json:
            raise RuntimeError(
                f"{variant} prompts: templates without the word 'json' "
                f"(DeepSeek json_object would reject them): {', '.join(without_json)}"
            )


def downgrade() -> None:
    """Downgrade schema: снять промпты и колонки, вернуть прежние версии roadmap."""
    bind = op.get_bind()
    now = datetime.now(UTC)

    for variant, (_, version) in _ROADMAP_VERSIONS.items():
        bind.execute(
            sa.text("DELETE FROM prompts WHERE key = 'plot_design' AND variant = :variant"),
            {"variant": variant},
        )
        bind.execute(
            sa.text(
                "DELETE FROM prompts "
                "WHERE key = 'roadmap' AND variant = :variant AND version = :version"
            ),
            {"variant": variant, "version": version},
        )
        # Возвращаем активность последней оставшейся версии roadmap.
        bind.execute(
            sa.text(
                "UPDATE prompts SET is_active = true, updated_at = :now "
                "WHERE key = 'roadmap' AND variant = :variant AND version = ("
                "  SELECT MAX(version) FROM prompts "
                "  WHERE key = 'roadmap' AND variant = :variant"
                ")"
            ),
            {"variant": variant, "now": now},
        )

    op.drop_column("novels", "plot_design")
    op.drop_column("roadmap", "beat_type")

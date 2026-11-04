"""Heat-квоты и дедлайны для nsfw_low/medium/high: plot_design v2 и roadmap v3

Revision ID: f4e5d6c7b8a9
Revises: e3b7c1d9a2f4
Create Date: 2026-11-04 13:00:00.000000

Предпосылка: после введения design-doc на вариантах 18+ эротика сместилась в конец
роадмапа. Причины в промптах: (1) plot_design режет эротическую нить правилом
«ни одна нить не ведёт больше половины шагов» и формулировкой «кинк — одна нить из
нескольких двигателей»; (2) у roadmap нет нижней квоты на интимные шаги (есть только
потолок «intimacy не должно превосходить plot-moving шаги»), а фраза «never let
intimacy become the story's sole purpose» читается моделью как «меньше секса»;
(3) правило «premise — это цель, а не стартовое состояние» откладывает эротическую
предпосылку в поздние шаги.

Что делает миграция (только варианты ``nsfw_low``, ``nsfw_medium``, ``nsfw_high``;
``default``, ``nsfw_extra`` и устаревший ``nsfw`` не трогаются):

- ``plot_design`` version 2: для взрослых вариантов политика разрешает эротической
  нити быть главным двигателем (снят потолок «не больше половины шагов», задан
  верхний предел 60/45/50% по уровням) и требует реального присутствия нити по всей
  дуге, а не одной поздней сценой.
- ``roadmap`` version 3: переиздаётся из базы version 2 (INSERT-трансформация —
  system_template v2 читается и дополняется перед JSON-схемой). Добавляются:
  - heat-бюджет уровня (минимум актов, дедлайн первого акта, максимум «сухих» серий,
    разметка beat_type) — нижняя квота, которой раньше не было;
  - блок порядка/материала: шаги хронологичны, события из запроса пользователя
    становятся спиной роадмапа в порядке запроса, правило «первое появление»
    относится к персонажам, а не к эротической предпосылке;
  - для ``nsfw_high`` заменяется деэскалирующая content-policy на формулировку с
    heat-бюджетом (эротика — главный двигатель, а не гарнир).

Схема и набор плейсхолдеров не меняются, код генераторов не затрагивается.
Миграция идемпотентна: roadmap читает фиксированную базу version 2, поэтому повторный
запуск после downgrade даёт тот же текст. Downgrade удаляет v3 roadmap и v2
plot_design и возвращает активность предыдущим версиям.
"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4e5d6c7b8a9'
down_revision: Union[str, Sequence[str], None] = 'e3b7c1d9a2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VARIANTS = ("nsfw_low", "nsfw_medium", "nsfw_high")

_PLOT_DESIGN_VERSION = 2
_ROADMAP_VERSION = 3

# База roadmap, из которой переиздаётся v3 (фиксированная версия для идемпотентности).
_ROADMAP_BASE_VERSION = 2

_SCHEMA_ANCHOR = "Answer STRICTLY as JSON matching this schema:"


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

_PLOT_DESIGN_POLICY: dict[str, str] = {
    "nsfw_high": (
        "Content policy: every character is an adult (18+). The design brief plans "
        "explicit intimate and erotic beats between consenting adults. The erotic/"
        "sexual thread may be the story's PRIMARY engine: the cap 'no single thread "
        "may have min_steps above half the planned step count' does not apply to it, "
        "and it may drive up to 60% of the steps. The remaining threads must be "
        "distinct engines (relationships, secrets, rules, rivalry, consequences) so "
        "the story is not a monotone repetition of one premise. Give the erotic "
        "thread a min_steps that reflects a real presence across the arc — the first "
        "explicit beat early, the peak before the finale — not a single late scene. "
        "Never involve minors."
    ),
    "nsfw_medium": (
        "Content policy: every character is an adult (18+). The design brief plans "
        "sensual and erotic beats between consenting adults (nudity, foreplay, a night "
        "together) shown without crude anatomy. The erotic/romantic thread may be a "
        "major engine: the cap 'no single thread may have min_steps above half the "
        "planned step count' does not apply to it, and it may drive up to 45% of the "
        "steps. The other threads must be distinct engines. Give the erotic thread a "
        "real presence across the arc — the first erotic beat by the middle, not only "
        "at the end. Never involve minors."
    ),
    "nsfw_low": (
        "Content policy: every character is an adult (18+). The design brief plans "
        "adult romance: attraction, tension, closeness and kisses, with no explicit "
        "acts. The romance/attraction thread may be a major engine: the cap 'no single "
        "thread may have min_steps above half the planned step count' does not apply "
        "to it, and it may drive up to half the steps. The other threads must be "
        "distinct engines. Give the romance thread a real presence from the start — "
        "charged beats spread across the arc, not only a confession at the end. "
        "Never involve minors."
    ),
}

_HEAT_BLOCK: dict[str, str] = {
    "nsfw_high": (
        "Heat budget — follow as a hard constraint:\n"
        "- If you plan N steps, at least 3 of them (and no fewer than a quarter of N) "
        "must be intimacy/escalation steps whose event IS a concrete explicit act "
        "(who does what to whom and how far it goes), not a lead-up, a kiss or an "
        "anticipation.\n"
        "- The first explicit act must land no later than step 3; do not save the "
        "first act for the finale.\n"
        "- At least 6 of N steps must carry heat (an explicit act or a charged erotic "
        "situation: being seen, a proposition, an erection, undressing); no more than "
        "2 consecutive steps without heat.\n"
        "- The peak act must land before the final step, so the last step shows its "
        "consequences.\n"
        "- Set beat_type = \"intimacy\" for steps whose event is the act itself, "
        "\"escalation\" for steps that raise the erotic stakes, and \"texture\" or "
        "\"obstacle\" for charged-but-not-explicit steps.\n"
        "- Use scenes_count = 2 for act steps so the act is not compressed into one scene."
    ),
    "nsfw_medium": (
        "Heat budget — follow as a hard constraint:\n"
        "- If you plan N steps, at least 2 of them must be erotic beats between "
        "consenting adults (a seduction, a night together, foreplay) shown sensually "
        "rather than graphically; the first must land by the middle of the story.\n"
        "- At least 4 of N steps must carry heat (desire, tension, an erotic "
        "situation); no more than 3 consecutive steps without heat.\n"
        "- Keep the erotic steps sensual: sensation, breath, warmth and reaction; do "
        "not spell out crude step-by-step mechanics.\n"
        "- Set beat_type = \"intimacy\" for the erotic steps and \"escalation\" where "
        "desire grows."
    ),
    "nsfw_low": (
        "Heat budget — follow as a hard constraint:\n"
        "- Heat is romantic tension, not explicit: glances, charged closeness, a kiss, "
        "an embrace. No nudity below the waist and no sexual acts.\n"
        "- The first charged beat must land no later than step 2, and at least a third "
        "of the steps must carry attraction or romantic tension.\n"
        "- At most 1-2 steps may end on a fade-to-black before anything explicit.\n"
        "- Set beat_type = \"intimacy\" for a kiss/closeness step and \"texture\" for "
        "charged tension."
    ),
}

_ORDER_BLOCK = (
    "Order and source material:\n"
    "- The steps are in CHRONOLOGICAL order: step 1 is the earliest event and the "
    "last step is the latest. A culmination (a confession, a night together, the "
    "peak act) must not appear before the steps that set it up.\n"
    "- If the user request contains a list of concrete events or scenes, use them as "
    "the spine: each listed event becomes its own step, in the order given, starting "
    "from the first steps. Build the threads and the remaining steps AROUND them — do "
    "not postpone them to the finale and do not replace them with a generic build-up.\n"
    "- The first-appearance rule applies to characters, not to the erotic premise: "
    "the story's erotic premise must be active from the first heat step, not built "
    "toward across the whole arc."
)

_HIGH_POLICY_OLD = (
    "Content policy: every character is an adult (18+); the story may include intimate "
    "and erotic beats between consenting adults. Such a beat still needs its own event, "
    "conflict and change and must move the plot forward — never let intimacy become "
    "the story's sole purpose."
)

_HIGH_POLICY_NEW = (
    "Content policy: every character is an adult (18+); the story includes explicit "
    "intimate and erotic beats between consenting adults, distributed across the arc "
    "according to the heat budget above. Each such beat still needs its own event, "
    "conflict and change; the erotic content is a primary engine of the story, not a "
    "garnish and not the sole purpose of every step."
)


_PLOT_DESIGN_USER = """Title: {title}
Description: {description}
Narrative tone: {tone}{characters_block}
User request: {user_prompt}"""

_ROADMAP_USER = """User request: {user_prompt}

Title: {title}
Description: {description}
Narrative tone: {tone}

Story shape (follow its beats in order):
{shape_block}

Design brief (thread budget and through-line):
{design_block}{place_time_catalog}{characters_block}"""


def _plot_design_system(variant: str) -> str:
    """System-шаблон plot_design v2: тело без изменений, политика по уровню."""
    return (
        "You are a professional story designer for adult (18+) visual novels. "
        + _PLOT_DESIGN_BODY
        + _PLOT_DESIGN_POLICY[variant]
        + "\n{russian_note}"
    )


def _roadmap_system(bind: sa.Connection, variant: str) -> str:
    """Roadmap v3 = база v2 + heat-бюджет + блок порядка; для high — замена политики."""
    base = bind.execute(
        sa.text(
            "SELECT system_template FROM prompts "
            "WHERE key = 'roadmap' AND variant = :variant AND version = :version"
        ),
        {"variant": variant, "version": _ROADMAP_BASE_VERSION},
    ).scalar_one()

    block = _HEAT_BLOCK[variant] + "\n\n" + _ORDER_BLOCK
    if _SCHEMA_ANCHOR in base:
        system = base.replace(_SCHEMA_ANCHOR, block + "\n\n" + _SCHEMA_ANCHOR, 1)
    else:
        system = base + "\n\n" + block

    if variant == "nsfw_high" and _HIGH_POLICY_OLD in system:
        system = system.replace(_HIGH_POLICY_OLD, _HIGH_POLICY_NEW, 1)
    return system


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
    """Upgrade schema: plot_design v2 и roadmap v3 для трёх nsfw-вариантов."""
    bind = op.get_bind()
    for variant in _VARIANTS:
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
            version=_ROADMAP_VERSION,
            system=_roadmap_system(bind, variant),
            user=_ROADMAP_USER,
        )
        for key in ("plot_design", "roadmap"):
            _assert_single_active(bind, key, variant)

    # DeepSeek при response_format=json_object отвечает 400, если в промпте нет
    # слова "json": проверяем на этапе миграции, а не в рантайме.
    for variant in _VARIANTS:
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
    """Downgrade schema: удалить v3 roadmap и v2 plot_design, вернуть прежние версии."""
    bind = op.get_bind()
    now = datetime.now(UTC)

    for variant in _VARIANTS:
        bind.execute(
            sa.text(
                "DELETE FROM prompts WHERE key = 'plot_design' AND variant = :variant "
                "AND version = :version"
            ),
            {"variant": variant, "version": _PLOT_DESIGN_VERSION},
        )
        bind.execute(
            sa.text(
                "DELETE FROM prompts WHERE key = 'roadmap' AND variant = :variant "
                "AND version = :version"
            ),
            {"variant": variant, "version": _ROADMAP_VERSION},
        )
        for key in ("plot_design", "roadmap"):
            bind.execute(
                sa.text(
                    "UPDATE prompts SET is_active = true, updated_at = :now "
                    "WHERE key = :key AND variant = :variant AND version = ("
                    "  SELECT MAX(version) FROM prompts "
                    "  WHERE key = :key AND variant = :variant"
                    ")"
                ),
                {"key": key, "variant": variant, "now": now},
            )

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI + Kafka service that generates interactive visual novel plots (story, characters, roadmap/branching
dialogue) via an LLM (DeepSeek, through an OpenAI-compatible client). Novel creation can be triggered over HTTP
or by consuming a Kafka event; generated content is persisted to Postgres via SQLAlchemy async + Alembic.

## Commands

There is no test suite and no linter/formatter config in this repo yet — don't assume `pytest`/`ruff`/`mypy`
targets exist; check before relying on them.

Local (no Docker), using `uv`:
```
uv sync
uv run uvicorn src.main.run:app --reload
```
Requires a `.env` (see `env.example` for the shape of `POSTGRES__*`, `KAFKA__*`, plus a `DEEPSEEK__API_KEY`
which is not in the example file) and a running Postgres + Kafka.

Docker Compose (the primary dev workflow):
```
make up          # build + start app and db_pg in the foreground
make upd         # same, detached
make just_up     # start without rebuilding
make down        # stop and remove containers
make stop        # stop without removing
```
Every `make` target that touches Docker first runs `docker-env` (`scripts/makefile/docker_env.sh`), which
**regenerates `.env`** from `env.example` + `.secrets` (git-ignored). Edit `env.example`/`.secrets`, never `.env`
directly — it's overwritten on the next `make` invocation.

Migrations (Alembic, `script_location = src/outbound/database`, run against the `app` container):
```
make migration m="Add novel models"   # autogenerate a revision
```
`docker-entrypoint.sh` runs `alembic upgrade head` automatically before starting uvicorn, so migrations apply on
container start; no separate "apply migrations" make target exists.

## Architecture

Hexagonal / ports-and-adapters, split into four top-level packages under `src/`:

- **`src/core`** — domain layer, framework-agnostic. Per-bounded-context subpackage (currently `novels`):
  - `models.py` — plain `@dataclass` domain entities (`Novel`, `Character`, `Roadmap`, `Scene`, `DialogueLine`,
    `DialogueAction`). These are distinct from both the SQLAlchemy ORM models and the Pydantic API schemas.
  - `interfaces.py` — `Protocol`s for repositories (`NovelRepositoryProtocol`, etc.) and for the LLM
    (`GeneratorProtocol.generate(prompt: list) -> dict`). Adapters satisfy these structurally, no inheritance.
  - `services/crud.py` — thin per-entity CRUD services (`NovelService`, `CharacterService`, ...), each wrapping
    one repository protocol.
  - `services/generate/` — LLM-backed generation services. `NovelGenerator` builds a system prompt, calls
    `GeneratorProtocol.generate`, expects strict JSON back, and persists the result. `CharacterGenerator` does
    the same for the character cast, given a persisted `Novel`.
  - `services/composition.py` — `NovelCompositionService.create()` orchestrates the two generators: generate the
    novel first, then generate characters for it.
  - `exceptions.py` — domain exceptions (`GenerationError`, `NovelNotFoundError`).

- **`src/inbound`** — driving adapters (things that call into `core`):
  - `http/` — FastAPI routers (`novels/router.py`, `health/`) and per-module `dependencies.py` that wire core
    services to concrete outbound adapters via `Depends()` chains. `root_router.py` assembles the app's router.
  - `kafka/` — `consumer.py` runs an `AIOKafkaConsumer` loop; `handlers/registry.py` maps Kafka topic →
    `(pydantic schema, handler fn)`; `handlers/plot_generation.py` handles `novel.events.create`. Because this
    path runs outside FastAPI's request scope, it wires services manually (`handlers/dependencies.py:
    build_novel_composition_service`) instead of using `Depends()`, and opens its own DB session via
    `get_session_scope()`.

- **`src/outbound`** — driven adapters (things `core` calls out to), implementing the `core.interfaces` protocols:
  - `ai/` — `client.py` builds/closes a module-level `AsyncOpenAI` client pointed at DeepSeek's OpenAI-compatible
    API; `deepseek_client.py`'s `DeepSeekGenerator` implements `GeneratorProtocol` (requests
    `response_format={"type": "json_object"}` and JSON-decodes the response).
  - `database/` — SQLAlchemy async models (`models/novels.py`), repositories (`repositories/novel_repository.py`)
    that translate ORM rows to/from `core.models` dataclasses via `_to_domain`, `session.py`/`dependencies.py`
    for engine/session management, and Alembic (`env.py`, `versions/`).
  - `kafka/` — `topic.py` (topic name constants) and `schemas/` (Pydantic message contracts, e.g.
    `NovelCreateRequested`).

- **`src/main`** — composition root: `config/settings.py` (pydantic-settings, `.env` + `__`-nested env vars,
  e.g. `POSTGRES__HOST`), `config/logging.py`, and `run.py` (builds the `FastAPI` app; its `lifespan` starts the
  Kafka consumer loop and the DeepSeek client on startup, and disposes the DB engine / stops the consumer on
  shutdown).

### Things to know when extending this

- Two entry points can trigger the same use case (novel creation): `POST /novels/` and the
  `novel.events.create` Kafka topic. They each build the same `NovelCompositionService` graph through their own
  wiring (`inbound/http/novels/dependencies.py` vs. `inbound/kafka/handlers/dependencies.py`) — when a
  constructor signature in `core/services` changes, both wiring sites need updating, not just one.
- Only `Novel` and `Character` have generation wired end-to-end. `Roadmap`, `Scene`, `DialogueLine`, and
  `DialogueAction` already have domain models, protocols, ORM models, and repositories, but no
  generator/service/route yet — that's the natural next slice of work.
- LLM prompts are built inline inside the generator classes (`__create_prompt`/`__create_promt`) as Russian-
  language system prompts instructing the model to return strict JSON matching a described schema. When adding
  a new generator, follow the same shape: build `[system_prompt, user_prompt]`, call
  `GeneratorProtocol.generate`, and validate/consume the returned dict defensively (the LLM is a trust boundary).

# AI Plot Generator

Сервис, который генерирует интерактивные визуальные новеллы с помощью LLM. По текстовому запросу пользователя
он придумывает новеллу, персонажей, роадмап сюжета, сцены и диалоги, сохраняет всё в Postgres и затем отдаёт
новеллу клиенту по одной реплике.

## Что умеет

- **Генерация новеллы по промпту.** Последовательно генерируются: описание новеллы → персонажи → роадмап
  (шаги сюжета) → первая сцена → диалог этой сцены → сжатое изложение истории (`story_context`).
- **Вселенные Codex.** Если в запросе передан `universe_id`, сервис сначала исследует базу знаний Codex
  (вселенная, персонажи, фоны, спрайты, эмоции, наряды) и строит новеллу на её основе. Реплики при этом
  получают ключи ассетов: фон, спрайт, наряд, эмоция.
- **Пошаговое проигрывание.** Клиент запрашивает реплики по одной. Когда сгенерированные реплики заканчиваются,
  а роадмап ещё не пройден, сервис догенерирует следующую сцену (по команде из Kafka).
- **Сжатое изложение истории.** После каждой сцены LLM обновляет `story_context` (краткое содержание, ключевые
  факты, состояние персонажей) — именно оно, а не полная история, передаётся в промпты следующих сцен и диалогов.
- **Трассировка LLM.** Все вызовы модели пишутся в `llm_logs/*.jsonl`, по ним можно собрать сводку токенов и
  посмотреть промпты/ответы.

Генерация новеллы запускается событием в Kafka; HTTP-ручки только читают данные и управляют проигрыванием.

## Стек

Python 3.14, FastAPI, SQLAlchemy (async) + Alembic, PostgreSQL, Kafka (aiokafka), DeepSeek через
OpenAI-совместимый клиент, pydantic-ai для агента, работающего с Codex. Зависимости управляются через `uv`,
тесты — pytest (asyncio, respx).

## Архитектура

Проект построен по гексагональной архитектуре (ports & adapters):

```
src/
├── core/       # домен без фреймворков: модели, протоколы (interfaces), сервисы и use case'ы
│   ├── novels/ # модели новеллы, сервисы генерации/проигрывания, use case'ы, трассировка LLM
│   ├── codex/  # модели и сервис Codex
│   ├── generation_jobs/ # задачи генерации (идемпотентность по job_id)
│   └── health/ # проверка состояния сервиса
├── inbound/    # входящие адаптеры: HTTP (FastAPI) и Kafka-консьюмер
├── outbound/   # исходящие адаптеры: Postgres, DeepSeek, Codex, Kafka-продюсер и схемы сообщений
└── main/       # точка сборки: настройки, логирование, создание FastAPI-приложения, фоновые задачи
```

### Пайплайн генерации

`core/novels/services/generate/` — по генератору на сущность, все наследуют `BaseGenerator` (оборачивает вызов LLM
и превращает ошибки в `GenerationError`). Порядок: novel → characters → roadmap → scene → dialogue → story_context.

- `composition.py` (`NovelCompositionService`) — создаёт новеллу целиком до первой сцены с диалогом.
- `continuation.py` (`SceneContinuationService`) — догенерирует следующую сцену по роадмапу.
- `playback.py` (`NovelPlaybackService`) — пошаговая выдача реплик; **никогда не вызывает LLM**, только читает БД
  и возвращает статус `ok` / `need_generation` / `generating` / `finished`.
- `story_context` — сжатое изложение прошедших сцен, передаётся в промпты следующих сцен/диалогов.
- `use_cases/` — сценарии генерации новеллы и сцены (идемпотентность по `job_id`, сохранение результата/ошибки).
- `llm_trace.py` — контекст трассировки (`llm_trace(operation)` + `trace.bind(novel_id)`, `llm_step(name)`),
  используется `outbound/ai/llm_log.py` для записи jsonl-логов.

## Запуск через Docker Compose

Это основной способ разработки.

### Что нужно заранее

- Docker и Docker Compose, `make`.
- Внешние Docker-сети `traefik` и `kafka`. Compose их не создаёт, а ожидает, что они уже существуют:
  в них должны работать Traefik и Kafka (брокер доступен как `kafka:9092`).
- Ключ API DeepSeek.
- Сервис Codex, если нужна генерация по вселенным (в `env.example` указан `http://codex-app-1:8000`).

Если сетей ещё нет, а Traefik и Kafka поднимаются отдельно, создай сети вручную:

```bash
docker network create traefik
docker network create kafka
```

### Настройка окружения

Файл `.env` **генерируется автоматически** при каждом вызове `make` (скрипт `scripts/makefile/docker_env.sh`)
из `env.example` и `.secrets`. Сам `.env` руками не редактируй: он будет перезаписан.

1. Общие (несекретные) настройки лежат в `env.example`.
2. Создай в корне проекта файл `.secrets` (он в `.gitignore`) с секретами:

   ```env
   POSTGRES__USER=postgres
   POSTGRES__PASSWORD=postgres
   DEEPSEEK__API_KEY=sk-...
   ```

### Старт

```bash
make up      # собрать и запустить в foreground
make upd     # то же, в фоне
```

При старте поднимаются:
- `db_pg` — Postgres 18 (снаружи доступен на порту `9877`);
- `migrations` — одноразовый контейнер, выполняет `alembic upgrade head`;
- `app` — сервис на uvicorn, стартует после успешных миграций.

Приложение доступно через Traefik по адресу http://ai_plot.localhost. Swagger-документация открывается
на http://ai_plot.localhost/docs.

### Другие команды

| Команда | Что делает |
|---|---|
| `make just_up` | запустить без пересборки |
| `make start` | запустить остановленные контейнеры |
| `make restart` | перезапустить контейнеры |
| `make stop` | остановить без удаления |
| `make down` | остановить и удалить контейнеры |
| `make migration m="Описание"` | сгенерировать новую миграцию Alembic (контейнер `app` должен быть запущен) |
| `make prune` | очистить Docker-ресурсы проекта |

## Запуск локально (без Docker)

Нужны запущенные Postgres и Kafka, а также `.env` с переменными (`POSTGRES__*`, `KAFKA__BOOTSTRAP_SERVERS`,
`DEEPSEEK__API_KEY`, при необходимости `CODEX__BASE_URL`). Хосты укажи такие, которые доступны с твоей машины.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn src.main.run:app --reload
```

## Тесты

```bash
uv run pytest
```

Настройки pytest (`asyncio_mode = "auto"`, `pythonpath = ["."]`) лежат в `pyproject.toml`. В `tests/` — unit-тесты
генераторов, сервисов, outbound-клиентов (DeepSeek, Codex) и состояния новеллы, а также фейковые репозитории
(`tests/fakes/`) и фабрики (`tests/factories/`).

## Переменные окружения

Вложенные настройки задаются через `__`, например `POSTGRES__HOST`.

| Переменная | Обязательна | Описание |
|---|---|---|
| `POSTGRES__DB`, `POSTGRES__HOST`, `POSTGRES__PORT` | да | подключение к Postgres |
| `POSTGRES__USER`, `POSTGRES__PASSWORD` | да | учётные данные Postgres (кладутся в `.secrets`) |
| `DEEPSEEK__API_KEY` | да | ключ DeepSeek (кладётся в `.secrets`) |
| `DEEPSEEK__BASE_URL` | нет | по умолчанию `https://api.deepseek.com` |
| `KAFKA__BOOTSTRAP_SERVERS` | нет | по умолчанию `kafka:9092` |
| `KAFKA__GROUP_ID` | нет | consumer group (по умолчанию `ai-plot`) |
| `KAFKA__CLIENT_ID` | нет | client id (по умолчанию `ai_plot_generator_client`) |
| `CODEX__BASE_URL` | нет | адрес сервиса Codex (по умолчанию в коде `http://codex.localhost`) |
| `CODEX__TIMEOUT` | нет | таймаут запросов к Codex, сек (по умолчанию `10`) |
| `APP__LOGGING_LEVEL` | нет | уровень логирования (по умолчанию `INFO`) |
| `APP__DEBUG_MODE` | нет | debug-режим (по умолчанию `false`) |
| `APP__ROOT_PATH` | нет | root path приложения за прокси (по умолчанию `/`) |

## API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/novels/` | список новелл (`?limit=&offset=`, ответ `items`/`total`/`limit`/`offset`) |
| `GET` | `/novels/{novel_id}` | получить новеллу |
| `DELETE` | `/novels/{novel_id}` | удалить новеллу (ответ `204`) |
| `GET` | `/novels/start/{novel_id}?offset={line_id}` | следующая реплика с персонажем и сценой |
| `GET` | `/health` | проверка состояния сервиса (статус Postgres) |

Как проигрывать новеллу: первый запрос делается без `offset`, дальше в `offset` передаётся `id` последней
полученной реплики. Ручка только читает из БД и никогда не вызывает LLM. Ответ всегда `200` с полем `status`
(`404` — нет новеллы или реплики `offset`):

```json
{"status": "ok", "step": {"dialogue": {...}, "scene": {...}, "character": {...}}}
{"status": "need_generation", "next_scene_order": 4}
{"status": "generating", "next_scene_order": 4}
{"status": "finished"}
```

`need_generation` — реплики кончились, но роадмап не пройден: нужно отправить в Kafka команду
`ai_plot.scene.generate` на сцену `next_scene_order` и после `done` повторить запрос с тем же `offset`.
`generating` — эта сцена уже генерируется.

## Kafka

Сервис слушает топики `ai_plot.novel.generate` и `ai_plot.scene.generate` (consumer group `ai-plot`)
и на каждую команду отвечает в `generation.results`. Offset коммитится вручную, только после отправки ответа.

Сгенерировать новеллу:

```json
{"job_id": 123, "prompt": "Детектив в викторианском Лондоне", "universe_id": null}
```

Сгенерировать следующую сцену (`scene_order` — сквозной номер сцены в новелле с 1, его отдаёт
`GET /novels/start/...` в `next_scene_order`):

```json
{"job_id": 124, "novel_id": 42, "scene_order": 4}
```

Результат (`result_id` — id новеллы или сцены):

```json
{"job_id": 124, "status": "done", "result_id": 987}
{"job_id": 124, "status": "failed", "error": "LLM timeout"}
```

Результат отправляется после коммита. Повторная доставка того же `job_id` переотправляет сохранённый
результат. Генерация сцены идемпотентна по `(novel_id, scene_order)`: уже готовая сцена сразу даёт `done`,
а команда на сцену, которая генерируется прямо сейчас, ждёт окончания (advisory-блокировка Postgres) и тоже
получает `done`. Ошибки сцены: `novel_finished` — роадмап пройден; сцена не по порядку — предыдущая
ещё не сгенерирована.

## Анализ запросов к LLM

Логи вызовов LLM пишутся в `llm_logs/*.jsonl` (по файлу на новеллу). Сводка и разбор — скриптом
`scripts/llm_report.py`:

```bash
uv run python scripts/llm_report.py             # итоги по всем новеллам
uv run python scripts/llm_report.py 42          # все запросы новеллы 42
uv run python scripts/llm_report.py 42 --full   # + тексты промптов и ответов
uv run python scripts/llm_report.py 42 --md     # промпты и ответы в llm_logs/novel_42.md
```

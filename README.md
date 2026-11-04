# AI Plot Generator

Сервис генерации интерактивных визуальных новелл на LLM (DeepSeek). По текстовому запросу строит новеллу:
описание → персонажи → design-doc → роадмап → сцены → диалоги, сохраняет данные в PostgreSQL и отдаёт новеллу
клиенту по одной реплике. Опционально генерация опирается на базу знаний Codex (вселенная, персонажи, ассеты).

## Возможности

- **Генерация новеллы по промпту.** Последовательность: novel → characters → plot_design → roadmap → сцена →
  диалог → `story_context`. `plot_design` — дешёвый проход design-doc (форма истории, нити с бюджетом шагов,
  сквозная линия, поворот), на который опирается роадмап; публикуется для всех вариантов, кроме `nsfw_extra`.
- **Вселенные Codex.** При `universe_id` сервис исследует базу знаний Codex (вселенная, персонажи, фоны, спрайты,
  эмоции, наряды) и резолвит для реплик ключи ассетов: фон, спрайт, наряд, эмоция, звук.
- **Пошаговое проигрывание.** Клиент получает реплики по одной. При исчерпании реплик и не пройденном роадмапе
  сервис догенерирует следующую сцену (команда из Kafka).
- **Ветвление.** В режиме `interactive` шаг роадмапа — узел дерева с вариантами выбора; выбор игрока фиксируется и
  ведёт в истинную или отдельно сгенерированную ветку.
- **Сжатый контекст истории.** После сцены LLM обновляет `story_context` (краткое содержание, факты, состояние
  персонажей). В промпты следующих сцен и диалогов передаётся только он, а не полная история.
- **Версионируемые промпты.** Шаблоны хранятся в таблице `prompts` (`key` × `variant` × `version`), правятся без
  передеплоя. Варианты: `default`, `nsfw_low`, `nsfw_medium`, `nsfw_high`, `nsfw_extra`; `nsfw` — устаревший алиас
  верхнего уровня.
- **Трассировка LLM.** Каждый вызов публикуется в `llm.usage` (токены, стоимость, латентность, ошибки, промпт и
  ответ).

Генерацию запускают события Kafka; HTTP-ручки читают данные, отдают реплики и фиксируют выбор игрока.

## Стек

Python 3.14, FastAPI, SQLAlchemy (async) + Alembic, PostgreSQL, Kafka (aiokafka), DeepSeek через
OpenAI-совместимый клиент, pydantic-ai (агент Codex). Зависимости — `uv`, тесты — `pytest` + `pytest-asyncio`.

## Архитектура

Гексагональная архитектура (ports & adapters): домен зависит от внешнего мира только через протоколы.

```
src/
├── core/       # домен без фреймворков: модели, протоколы (interfaces), сервисы, use case'ы
│   ├── novels/ # модели новеллы, генерация/проигрывание, трассировка LLM
│   ├── codex/  # модели и сервис Codex
│   ├── generation_jobs/ # идемпотентность по job_id
│   └── health/
├── inbound/    # адаптеры: HTTP (FastAPI), Kafka-консьюмер
├── outbound/   # адаптеры: Postgres (миграции в database/versions), DeepSeek, Codex, Kafka
└── main/       # сборка: настройки, логирование, приложение, фоновые задачи
```

### Пайплайн генерации

`core/novels/services/` разделены по роли:

- `crud.py` — фасады над репозиториями (`NovelService`, `CharacterService`, `SceneService`, …).
- `generation/`:
  - `generators/` — по генератору на сущность, все наследуют `BaseGenerator` (оборачивает вызов LLM в `llm_step`,
    ошибки превращает в `GenerationError`); порядок: novel → characters → plot_design → roadmap → scene → dialogue →
    story_context. `plot_design` — один дешёвый вызов (`think=False`): выбирает форму из библиотеки
    `prompts/shapes.py`, называет 3–5 нитей с бюджетом шагов и сохраняет снапшот в `novels.plot_design`; роадмап
    получает форму и design-doc как ограничения и помечает каждый шаг `beat_type`;
  - `composition.py` (`NovelCompositionService`) — сборка новеллы до первой сцены с диалогом;
  - `continuation.py` (`SceneContinuationService`) — догенерация следующей сцены по роадмапу; сцену, уже
    записанную без реплик (воркер упал между сценой и диалогом), достраивает, а не отдаёт готовой;
  - `state.py` (`NovelState`) — снапшот роадмапа/сцен/реплик и расчёт следующего слота;
  - `assets.py` (`SceneAssetService`) — резолв спрайтов/фонов/одежды/эмоций из Codex;
  - `prompts/` — форматтеры промптов (текст, состав персонажей, контекст вселенной), библиотека нарративных форм
    (`shapes.py`) и каталог шаблонов из БД.
- `playback/` (`NovelPlaybackService`) — выдача реплик; LLM не вызывает, только читает БД и возвращает статус
  `ok` / `need_generation` / `generating` / `finished`.
- `use_cases/` — сценарии генерации новеллы/сцены/ветки и выбора игрока (идемпотентность по `job_id`, сохранение
  результата или ошибки).
- `llm_trace.py` — контекст трассировки (`llm_trace(operation)` + `trace.bind(novel_id)`, `llm_step(name)`),
  используется `outbound/ai/llm_log.py`.

## Запуск через Docker Compose

Основной режим разработки.

### Требования

- Docker, Docker Compose, `make`.
- Внешние Docker-сети `traefik` и `kafka`, которые Compose ожидает существующими (в них работают Traefik и
  Kafka, брокер доступен как `kafka:9092`).
- Ключ API DeepSeek.
- Сервис Codex — если нужна генерация по вселенным (`env.example`: `http://codex-app-1:8000`).

Создание сетей, если их ещё нет:

```bash
docker network create traefik
docker network create kafka
```

### Настройка окружения

`.env` **генерируется** при каждом `make` (скрипт `scripts/makefile/docker_env.sh`) из `env.example` и `.secrets`;
ручные правки `.env` перезаписываются.

1. Несекретные настройки — в `env.example`.
2. Секреты — в `.secrets` (в `.gitignore`):

   ```env
   POSTGRES__USER=postgres
   POSTGRES__PASSWORD=postgres
   DEEPSEEK__API_KEY=sk-...
   ```

### Старт

```bash
make up      # сборка и запуск, foreground
make upd     # то же, в фоне
```

Поднимаемые контейнеры:

- `db_pg` — PostgreSQL 18, наружу порт `9877`;
- `migrations` — одноразовый контейнер, `alembic upgrade head`;
- `app` — uvicorn, стартует после успешных миграций.

Приложение доступно через Traefik: http://ai_plot.localhost, Swagger — http://ai_plot.localhost/docs.

### Команды

| Команда | Действие |
|---|---|
| `make just_up` | запуск без пересборки |
| `make start` | запуск остановленных контейнеров |
| `make restart` | перезапуск контейнеров |
| `make stop` | остановка без удаления |
| `make down` | остановка и удаление контейнеров |
| `make migration m="Описание"` | autogenerate-миграция Alembic (нужен запущенный `app`) |
| `make prune` | очистка Docker-ресурсов проекта |

## Запуск локально (без Docker)

Нужны PostgreSQL и Kafka, а также `.env` с `POSTGRES__*`, `KAFKA__BOOTSTRAP_SERVERS`, `DEEPSEEK__API_KEY`
(и `CODEX__BASE_URL` при работе с Codex). Хосты — доступные с машины разработчика.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn src.main.run:app --reload
```

## Тесты

```bash
uv run pytest
```

Конфигурация pytest (`asyncio_mode = "auto"`, `pythonpath = ["."]`) — в `pyproject.toml`. В `tests/unit` — тесты
генераторов, сервисов, outbound-клиентов (DeepSeek, Codex) и состояния новеллы; фикстуры — `tests/fakes/`,
`tests/factories/`.

## Переменные окружения

Вложенные настройки задаются через `__` (например, `POSTGRES__HOST`).

| Переменная | Обязательна | Описание |
|---|---|---|
| `POSTGRES__DB`, `POSTGRES__HOST`, `POSTGRES__PORT` | да | подключение к PostgreSQL |
| `POSTGRES__USER`, `POSTGRES__PASSWORD` | да | учётные данные PostgreSQL (в `.secrets`) |
| `POSTGRES__POOL_SIZE`, `POSTGRES__MAX_OVERFLOW`, `POSTGRES__POOL_TIMEOUT_S` | нет | пул соединений: размер / overflow / таймаут взятия (`10` / `10` / `30`) |
| `DEEPSEEK__API_KEY` | да | ключ DeepSeek (в `.secrets`) |
| `DEEPSEEK__BASE_URL` | нет | `https://api.deepseek.com` |
| `DEEPSEEK__TIMEOUT_S` | нет | таймаут вызова LLM, с (`300`) |
| `DEEPSEEK__MAX_RETRIES` | нет | ретраи SDK на 429/5xx/сетевые ошибки (`3`) |
| `KAFKA__BOOTSTRAP_SERVERS` | нет | `kafka:9092` |
| `KAFKA__GROUP_ID` | нет | consumer group (`ai-plot`) |
| `KAFKA__CLIENT_ID` | нет | client id (`ai_plot_generator_client`) |
| `KAFKA__MAX_POLL_INTERVAL_MS` | нет | максимальный интервал между poll, мс (`900000`) |
| `CODEX__BASE_URL` | нет | адрес Codex (`http://codex.localhost`) |
| `CODEX__TIMEOUT` | нет | таймаут запросов к Codex, с (`10`) |
| `APP__LOGGING_LEVEL` | нет | уровень логирования (`INFO`) |
| `APP__DEBUG_MODE` | нет | debug-режим (`false`) |
| `APP__ROOT_PATH` | нет | root path за прокси (`/`) |
| `GENERATION__MAX_CONCURRENCY` | нет | одновременные команды генерации (`50`) |
| `GENERATION__MAX_RETRIES` | нет | ретраи сообщения на транзиентных ошибках (`3`) |
| `GENERATION__RETRY_BASE_DELAY_S`, `GENERATION__RETRY_MAX_DELAY_S` | нет | backoff ретраев (`1.0` / `30.0`) |
| `GENERATION__DLQ_TOPIC` | нет | топик мёртвых сообщений (`ai_plot.generation.dlq`) |

## API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/novels/` | список новелл (`?limit=&offset=`), ответ: `items`/`total`/`limit`/`offset` |
| `GET` | `/novels/{novel_id}` | новелла |
| `DELETE` | `/novels/{novel_id}` | удаление новеллы (`204`) |
| `GET` | `/novels/start/{novel_id}?offset={line_id}` | следующая реплика с персонажем и сценой |
| `POST` | `/novels/{novel_id}/choice` | фиксирует выбор игрока (`status`: `ok` / `need_branch_generation`) |
| `GET` | `/health` | состояние сервиса (PostgreSQL) |

Проигрывание: первый запрос — без `offset`, далее `offset` = `id` последней полученной реплики. Ручка только
читает БД, LLM не вызывает; ответ всегда `200` с полем `status` (`404` — нет новеллы или реплики `offset`):

```json
{"status": "ok", "step": {"dialogue": {...}, "scene": {...}, "character": {...}}}
{"status": "need_generation", "next_roadmap_id": 5, "next_position": 2}
{"status": "generating", "next_roadmap_id": 5, "next_position": 2}
{"status": "finished"}
```

- `need_generation` — реплики исчерпаны, роадмап не пройден: отправить в Kafka `ai_plot.scene.generate` для сцены
  `(next_roadmap_id, next_position)`, после `done` повторить запрос с тем же `offset`;
- `generating` — сцена уже генерируется (или её диалог ещё пишется);
- `finished` — новелла пройдена: все шаги сыгранного пути закрыты, у их сцен есть реплики, а на развилках пути
  зафиксирован выбор. Сцена коммитится до генерации диалога, поэтому, пока реплики сцены ещё не записаны, вместо
  `finished` возвращается `need_generation`/`generating` для этой сцены.

Выбор игрока: тело `POST /novels/{novel_id}/choice` — `{"roadmap_choice_id": 12, "dialogue_line_id": 987}`. Ответ
`ok` — продолжение готово (истинный вариант или уже сгенерированная ветка); `need_branch_generation` — клиент
отправляет в `ai_plot.branch.generate` команду генерации ветки и повторяет запрос после `done`.

## Админка (SQLAdmin)

Доступна на `/admin`. Учётные данные — `ADMIN__USERNAME` / `ADMIN__PASSWORD` (`admin` / `admin`), секрет сессии —
`ADMIN__SECRET_KEY` (в продакшене обязателен собственный). Отключение — `ADMIN__ENABLED=false`.

Разделы:

- **Промпты** — CRUD таблицы `prompts`. Создание добавляет версию пары `(key, variant)` (`version = max + 1`) и
  деактивирует предыдущую активную; установка `is_active` гасит остальные активные версии той же пары. Шаблоны
  хранятся только в БД, правки применяются сразу.
  Градация 18+ по нарастанию откровенности: `nsfw_low` (романтика, намёки, затемнение), `nsfw_medium` (чувственная
  эротика без грубой анатомии), `nsfw_high` (откровенная физика). `nsfw_extra` — тестовый режим «чистый секс»:
  драматургия исключена (круг Хармона, арки, конфликт/кризис шага), роадмап состоит из шагов-актов, описание сцены —
  бриф акта, диалог пишет сцену от первого касания до оргазма. Комплект опубликован миграцией `d1e2f3a4b5c6` как
  `nsfw_extra` version 1; `nsfw_high` остаётся на version 2 (`scene`, `dialogue`) и version 1 остальных ключей.
  Устаревший `nsfw` сохранён для обратной совместимости API; новые новеллы создаются с `nsfw_high` (или
  `nsfw_extra` для тестов).
  Миграция `e3b7c1d9a2f4` добавляет шаг `plot_design` (version 1) и переиздаёт `roadmap` для `default`, `nsfw_low`,
  `nsfw_medium` и `nsfw_high`: роадмап получает форму истории из библиотеки `prompts/shapes.py` и design-doc с
  бюджетом нитей вместо жёсткого круга Хармона, а каждый шаг помечается `beat_type`. Пользовательский запрос
  фетиша/предпосылки становится одной из нитей, поэтому история не сводится к её повторению. `nsfw_extra` и
  устаревший `nsfw` миграция не трогает.
  Миграция `f4e5d6c7b8a9` добавляет heat-квоты и дедлайны для трёх nsfw-вариантов: `plot_design` version 2
  разрешает эротической нити быть главным двигателем (снят потолок «не больше половины шагов»), а `roadmap`
  version 3 задаёт нижнюю квоту интимных шагов (минимум актов, дедлайн первого акта, максимум «сухих» серий,
  разметка `beat_type`), требует хронологичности и делает события из запроса спиной роадмапа. Библиотека
  `prompts/shapes.py` получает форму `erotic_escalation` (`adult_only`) и поле `heat_note` у каждой формы.
- **Тест диалога** — перегенерация диалога сцены (`scene_id`) в процессе с выбором варианта промпта и/или мока.
  `render_only` собирает промпт тем же `DialoguePromptBuilder`, что и прод, без вызова LLM; генерация идёт через
  общий `DeepSeekGenerator` без аналитики. В БД ничего не пишется. Полная генерация новеллы — CLI-скрипт
  `scripts/generate_novel.py`.

## Kafka

Топики: `ai_plot.novel.generate`, `ai_plot.scene.generate`, `ai_plot.branch.generate` (consumer group `ai-plot`);
ответы — в `generation.results`. Команды обрабатываются параллельно в пределах `GENERATION__MAX_CONCURRENCY`;
offset коммитится вручную по водяному знаку непрерывно завершённого префикса партиции (at-least-once). Сцены одной
новеллы сериализуются по `novel_id`, разные новеллы генерируются параллельно. После исчерпания ретраев сообщение
уходит в `GENERATION__DLQ_TOPIC`.

Генерация новеллы:

```json
{"job_id": 123, "prompt": "Детектив в викторианском Лондоне", "universe_id": null}
```

Генерация следующей сцены (`scene_order` — сквозной номер сцены в новелле с 1, отдаётся в `next_scene_order`):

```json
{"job_id": 124, "novel_id": 42, "scene_order": 4}
```

Результат (`result_id` — id новеллы, сцены или ветки):

```json
{"job_id": 124, "status": "done", "result_id": 987}
{"job_id": 124, "status": "failed", "error": "LLM timeout"}
```

Инварианты:

- результат отправляется после коммита;
- повторная доставка `job_id` переотправляет сохранённый результат;
- генерация сцены идемпотентна по `(novel_id, scene_order)`: готовая сцена сразу даёт `done`, команда на
  генерируемую сейчас сцену ждёт завершения (advisory-блокировка PostgreSQL) и получает `done`.

Ошибки сцены: `novel_finished` — роадмап пройден; сцена не по порядку — предыдущая не сгенерирована.

## Аналитика LLM

Метрики вызовов (токены, стоимость, латентность, ошибки), промпты (`messages`) и ответы (`response`) публикуются в
`llm.usage` и накапливаются в `llm-analytics` (ClickHouse + Grafana). При недоступности Kafka события пишутся в
`llm_logs/outbox.jsonl` и досылаются при следующем дренаже.

Ранее записанные `llm_logs/*.jsonl` этим сервисом не импортируются — публикуются только новые вызовы. Просмотр
токенов/стоимости и промптов/ответов — в `llm-analytics` (Grafana, ClickHouse).

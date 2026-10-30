from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.outbound.kafka.topic import Topics


class AppSettings(BaseModel):
    SERVICE_NAME: str = "AI Plot Generator"
    # Машинный идентификатор сервиса для аналитики (env: APP__SERVICE_ID)
    SERVICE_ID: str = "ai_plot_generator"
    ROOT_PATH: str = "/"
    DEBUG_MODE: bool = False
    LOGGING_LEVEL: str = "INFO"


class PostgresSettings(BaseModel):
    DB: str
    HOST: str
    PORT: int
    USER: str
    PASSWORD: str

    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 10
    POOL_TIMEOUT_S: int = 30

    @property
    def dsn(self) -> str:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.USER,
            password=self.PASSWORD,
            host=self.HOST,
            port=self.PORT,
            path=f"{self.DB}",
        ).unicode_string()


class DeepSeekSettings(BaseSettings):
    API_KEY: str
    BASE_URL: str = "https://api.deepseek.com"
    TEMPERATURE: float = 0.9

    DIALOGUE_TEMPERATURE: float = 1.0

    # Модель по умолчанию
    MODEL: str = "deepseek-flash"

    NOVEL_MODEL: str = "deepseek-v4-pro"
    ROADMAP_MODEL: str = "deepseek-v4-pro"
    SCENE_MODEL: str = "deepseek-v4-pro"

    NOVEL_REASONING_EFFORT: str = "high"
    CHARACTER_REASONING_EFFORT: str = "low"
    ROADMAP_REASONING_EFFORT: str = "low"
    DIALOGUE_REASONING_EFFORT: str = "low"

    # Тумблеры thinking mode
    CHARACTER_THINK: bool = False
    ROADMAP_THINK: bool = True
    DIALOGUE_THINK: bool = True

    SCENE_VALIDATION_RETRIES: int = 3
    DIALOGUE_VALIDATION_RETRIES: int = 3

    # Таймаут одного вызова и число ретраев SDK (429/5xx/сетевые ошибки).
    TIMEOUT_S: float = 300.0
    MAX_RETRIES: int = 3


class CodexSettings(BaseSettings):
    BASE_URL: str = "http://codex.localhost"
    TIMEOUT: float = 10.0


class RedisSettings(BaseSettings):
    URL: str = "redis://redis:6379/0"

    CODEX_TTL_S: int = 1800
    CODEX_MATCH_TTL_S: int = 300


class KafkaSettings(BaseSettings):
    BOOTSTRAP_SERVERS: str = "kafka:9092"
    CLIENT_ID: str = "ai_plot_generator_client"
    GROUP_ID: str = "ai-plot"

    # Максимальный интервал между poll(). При долгой генерации пул занят и мы не
    # поллим, поэтому поднимаем, чтобы координатор не выкидывал консьюмера из группы.
    MAX_POLL_INTERVAL_MS: int = 900000


class AnalyticsSettings(BaseSettings):
    """Настройки отправки событий использования LLM в сервис аналитики."""

    # Топик, в который публикуются события (env: ANALYTICS__KAFKA_TOPIC)
    KAFKA_TOPIC: str = Topics.LLM_USAGE

    # Локальный outbox на случай недоступности Kafka: события дописываются в файл
    # и досылаются при следующем дренаже. (env: ANALYTICS__SPOOL_DIR / SPOOL_FILE)
    SPOOL_DIR: str = "llm_logs"
    SPOOL_FILE: str = "outbox.jsonl"

    # Период дренажа очереди/outbox (сек) и параметры ретрая отправки.
    FLUSH_INTERVAL_S: float = 1.0
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_S: float = 0.5
    QUEUE_SIZE: int = 10000


class GenerationSettings(BaseModel):
    """Параллельная обработка задач генерации."""

    # Максимум одновременно обрабатываемых сообщений. DeepSeek допускает до 500
    # (pro) / 2500 (flash) одновременных запросов на аккаунт. Генераторы разбивают
    # работу на короткие read/write-транзакции, а LLM вызывают между ними, поэтому
    # соединение Postgres держится лишь доли секунды на чтение/запись, и потолок
    # параллелизма задаёт лимит LLM-аккаунта (и ресурсы Redis/Kafka), а не пул БД.
    # 50 ≈ до ~50 одновременных новелл × несколько LLM-вызовов на шаг — с запасом
    # под лимит pro-модели (500); при необходимости поднимайте вплоть до ~100.
    MAX_CONCURRENCY: int = 50
    # Ретраи сообщения при транзиентных ошибках; после исчерпания — в DLQ.
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY_S: float = 1.0
    RETRY_MAX_DELAY_S: float = 30.0
    DLQ_TOPIC: str = "ai_plot.generation.dlq"

    # TTL Redis-блокировок генерации. Watchdog продлевает TTL каждые ``ttl/3`` сек,
    # пока воркер держит лок, поэтому TTL задаёт лишь время обнаружения упавшего
    # воркера, а не верхнюю границу генерации.
    JOB_LOCK_TTL_S: int = 60
    SCENE_LOCK_TTL_S: int = 60
    # Ожидание, когда джоб/сцена уже обрабатывается другим воркером. Дубль ждёт,
    # пока оригинал допишет DONE/FAILED (или отдаст сцену), иначе раньше времени
    # уйдёт в Kafka-ретраи/DLQ.
    IN_PROGRESS_POLL_INTERVAL_S: float = 1.0
    IN_PROGRESS_TIMEOUT_S: float = 1200.0
    # Таймаут блокирующего захвата блокировки сцены (аналог старой advisory-блокировки).
    # Согласован с IN_PROGRESS_TIMEOUT_S: оба покрывают худшее время генерации.
    SCENE_LOCK_ACQUIRE_TIMEOUT_S: float = 1200.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )

    app: AppSettings = AppSettings()
    postgres: PostgresSettings
    deepseek: DeepSeekSettings
    kafka: KafkaSettings
    codex: CodexSettings = CodexSettings()
    redis: RedisSettings = RedisSettings()
    analytics: AnalyticsSettings = AnalyticsSettings()
    generation: GenerationSettings = GenerationSettings()


settings = Settings()

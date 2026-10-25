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
    # Отдельная температура для диалогов: выше — разнообразнее и живее реплики.
    # 1.5 даёт слишком частый невалидный JSON, поэтому держим в безопасном диапазоне.
    DIALOGUE_TEMPERATURE: float = 1.0

    NOVEL_REASONING_EFFORT: str = "high"
    CHARACTER_REASONING_EFFORT: str = "low"
    ROADMAP_REASONING_EFFORT: str = "low"
    DIALOGUE_REASONING_EFFORT: str = "low"

    # Тумблеры thinking mode (deepseek). False = thinking выключен, reasoning
    # не генерируется и не тарифицируется. На структурированных JSON-шагах
    # (персонажи, роадмап) мышление почти не даёт прироста качества, но жжёт
    # ~40-50% выходных токенов.
    CHARACTER_THINK: bool = False
    ROADMAP_THINK: bool = True
    DIALOGUE_THINK: bool = True

    SCENE_VALIDATION_RETRIES: int = 3
    # Лимит полных ретраев диалога при неисправимых дефектах (после точечного ремонта).
    DIALOGUE_VALIDATION_RETRIES: int = 3


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


settings = Settings()

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
    # Уровень reasoning для шагов с включённым thinking (low/high/max).
    # Scene и StoryContext генерируются с thinking=disabled, поэтому effort им не нужен.
    NOVEL_REASONING_EFFORT: str = "high"
    CHARACTER_REASONING_EFFORT: str = "low"
    ROADMAP_REASONING_EFFORT: str = "high"
    DIALOGUE_REASONING_EFFORT: str = "high"


class CodexSettings(BaseSettings):
    BASE_URL: str = "http://codex.localhost"
    TIMEOUT: float = 10.0


class KafkaSettings(BaseSettings):
    BOOTSTRAP_SERVERS: str = "kafka:9092"
    CLIENT_ID: str = "ai_plot_generator_client"
    GROUP_ID: str = "ai-plot"


class AnalyticsSettings(BaseSettings):
    """Настройки отдельного сервиса аналитики использования LLM."""

    # Топик, в который публикуются события (env: ANALYTICS__KAFKA_TOPIC)
    KAFKA_TOPIC: str = Topics.LLM_USAGE


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
    analytics: AnalyticsSettings = AnalyticsSettings()


settings = Settings()

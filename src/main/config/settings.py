from pydantic import BaseModel, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    SERVICE_NAME: str = "AI Plot Generator"
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


class KafkaSettings(BaseSettings):
    BOOTSTRAP_SERVERS: str = "kafka:9092"
    CLIENT_ID: str = "my-choice-api"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )

    app: AppSettings = AppSettings()
    postgres: PostgresSettings
    deepseek: DeepSeekSettings
    kafka: KafkaSettings


settings = Settings()

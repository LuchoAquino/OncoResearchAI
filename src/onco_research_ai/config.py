from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: int = 5432
    qdrant_http_port: int = 6333

    @property
    def postgres_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host="localhost",
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def qdrant_url(self) -> str:
        return f"http://localhost:{self.qdrant_http_port}"


settings = Settings()
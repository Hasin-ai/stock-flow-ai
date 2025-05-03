from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration: int = 3600
    alphavantage_api_key: str
    gemini_api_key: str
    frontend_url: str = "http://localhost:3000"
    websocket_url: str = "ws://localhost:8000"
    qdrant_url: str = "http://localhost:6333"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
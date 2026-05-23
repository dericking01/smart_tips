from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    REDIS_HOST: str
    REDIS_PORT: int

    SMS_HOST: str
    SMS_PORTS: str
    SMS_TPS: int = 200

    SMS_USERNAME: str
    SMS_PASSWORD: str
    SMS_FROM: str

    class Config:
        env_file = ".env"

settings = Settings()
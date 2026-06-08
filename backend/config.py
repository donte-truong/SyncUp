from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./syncup.db", env="DATABASE_URL")
    google_client_id: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="http://localhost:8000/google/auth/callback", env="GOOGLE_REDIRECT_URI")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    gmail_sync_query: str = Field(default="label:bookings OR label:travel OR label:flights OR subject:(booking OR flight OR hotel)", env="GMAIL_SYNC_QUERY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

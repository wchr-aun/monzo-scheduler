"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class Settings:
    monzo_client_id: str
    monzo_client_secret: str = field(repr=False)
    monzo_redirect_uri: str
    database_url: str = "sqlite:///./monzo_scheduler.db"
    jwt_secret_key: str = field(default="", repr=False)
    jwt_expiration_seconds: int = 86400
    session_cookie_secure: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv(dotenv_path=ENV_FILE, override=False)
        return cls(
            monzo_client_id=os.getenv("MONZO_CLIENT_ID", ""),
            monzo_client_secret=os.getenv("MONZO_CLIENT_SECRET", ""),
            monzo_redirect_uri=os.getenv(
                "MONZO_REDIRECT_URI", "http://127.0.0.1:8000/monzo-callback"
            ),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./monzo_scheduler.db"),
            jwt_secret_key=os.getenv("JWT_SECRET_KEY", ""),
            jwt_expiration_seconds=int(os.getenv("JWT_EXPIRATION_SECONDS", "86400")),
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
                                  in {"1", "true", "yes"},
        )

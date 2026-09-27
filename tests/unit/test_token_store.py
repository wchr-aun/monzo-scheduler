import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, MonzoCredential
from app.schemas.monzo import MonzoTokenResponse
from app.services.token_store import save_monzo_tokens


@pytest.mark.parametrize(
    "token_response",
    [
        None,
        {},
        {"access_token": "token", "expires_in": 60},
        {"user_id": "user-1", "expires_in": 60},
        {"user_id": "user-1", "access_token": "", "expires_in": 60},
        {"access_token": "token", "expires_in": 0, "user_id": "user-1"},
        {
            "user_id": "user-1",
            "access_token": "token",
            "expires_in": 60,
            "refresh_token": 123,
        },
    ],
)
def test_token_response_model_rejects_invalid_monzo_response(token_response):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MonzoTokenResponse.model_validate(token_response)


def test_save_tokens_requires_jwt_secret(settings):
    settings = settings.__class__(
        settings.monzo_client_id,
        settings.monzo_client_secret,
        settings.monzo_redirect_uri,
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            save_monzo_tokens(
                MonzoTokenResponse(
                    user_id="user-1", access_token="secret", expires_in=60
                ),
                session,
                settings,
            )
        assert session.get(MonzoCredential, "user-1") is None
    engine.dispose()


def test_save_tokens_supports_optional_refresh_token(settings):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        signed_token = save_monzo_tokens(
            MonzoTokenResponse(
                user_id="user-1", access_token="access", expires_in=60
            ),
            session,
            settings,
        )
        saved = session.get(MonzoCredential, "user-1")
        assert signed_token
        assert saved.refresh_token is None
        assert saved.access_token == "access"
    engine.dispose()

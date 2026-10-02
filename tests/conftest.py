import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.config import Settings
from app.db.models import Base
from app.main import create_app


@pytest.fixture
def settings():
    return Settings(
        monzo_client_id="test-client-id",
        monzo_client_secret="test-client-secret",
        monzo_redirect_uri="http://testserver/monzo-callback",
        jwt_secret_key="test-jwt-signing-secret-for-tests-only",
        token_encryption_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )


@pytest.fixture
def client(settings):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    application = create_app(settings, engine=engine)
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()

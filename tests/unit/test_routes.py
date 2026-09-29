from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.main import create_app
from app.routers import monzo, tasks
from app.routers.resources import MonzoSession, monzo_session
from app.schemas.tasks import ScheduleTransferRequest


@contextmanager
def _client_for_settings(settings):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with TestClient(create_app(settings, engine=engine)) as client:
        yield client
    engine.dispose()


def test_health_route(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"message": "ok"}


def test_schedule_transfer_calls_scheduler_service(monkeypatch, client):
    scheduled_for = datetime(2030, 1, 1, 9, 30, tzinfo=timezone.utc)
    setup = type("Setup", (), {"setup_id": "setup-123"})()
    transfer = type("Transfer", (), {"transfer_id": "transfer-123"})()
    job = type("Job", (), {"next_run_time": scheduled_for})()
    called = {}

    def fake_schedule(scheduler, session_factory, settings, user_id, request):
        called.update(
            scheduler=scheduler,
            session_factory=session_factory,
            settings=settings,
            user_id=user_id,
            request=request,
        )
        return setup, transfer, job

    monkeypatch.setattr(tasks, "schedule_transfer", fake_schedule)
    client.app.dependency_overrides[monzo_session] = lambda: MonzoSession(
        user_id="user_123", access_token="unused"
    )
    response = client.post(
        "/schedule-transfer",
        json={
            "datetime": "2030-01-01T09:30:00Z",
            "interval": "weekly",
            "type": "withdraw",
            "amount": 500,
            "pot_id": "pot_123",
            "account_id": "acc_123",
        },
    )
    client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "scheduled",
        "setup_id": "setup-123",
        "transfer_id": "transfer-123",
        "next_run_at": scheduled_for.isoformat().replace("+00:00", "Z"),
    }
    assert called["scheduler"] is client.app.state.scheduler
    assert called["session_factory"] is client.app.state.session_factory
    assert called["settings"] is client.app.state.settings
    assert called["user_id"] == "user_123"
    assert isinstance(called["request"], ScheduleTransferRequest)
    assert called["request"].type == "withdraw"


def test_get_scheduled_transfers_calls_scheduler_service(monkeypatch, client):
    scheduled_for = datetime(2030, 1, 1, 9, 30, tzinfo=timezone.utc)
    transfer = type(
        "ScheduledTransferDetails",
        (),
        {
            "setup_id": "setup-123",
            "transfer_id": "transfer-123",
            "scheduled_for": scheduled_for,
            "interval": "weekly",
            "transfer_type": "withdraw",
            "amount": 500,
            "pot_id": "pot-123",
            "account_id": "account-123",
        },
    )()
    called = {}

    def fake_list(session_factory, user_id):
        called.update(session_factory=session_factory, user_id=user_id)
        return [transfer]

    monkeypatch.setattr(tasks, "list_scheduled_transfers", fake_list)
    client.app.dependency_overrides[monzo_session] = lambda: MonzoSession(
        user_id="user_123", access_token="unused"
    )

    response = client.get("/scheduled-transfers")
    client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "setup_id": "setup-123",
            "transfer_id": "transfer-123",
            "scheduled_for": scheduled_for.isoformat().replace("+00:00", "Z"),
            "interval": "weekly",
            "type": "withdraw",
            "amount": 500,
            "pot_id": "pot-123",
            "account_id": "account-123",
        }
    ]
    assert called["session_factory"] is client.app.state.session_factory
    assert called["user_id"] == "user_123"


def test_create_task_endpoint_is_removed(client):
    response = client.post("/create-task")

    assert response.status_code == 404


def test_monzo_redirect_requires_client_id(settings):
    settings = settings.__class__(
        "", settings.monzo_client_secret, settings.monzo_redirect_uri
    )

    with _client_for_settings(settings) as client:
        response = client.get("/monzo-redirect")

    assert response.status_code == 503
    assert response.json()["detail"] == "Monzo OAuth is not configured"


def test_monzo_callback_rejects_unknown_state(client):
    response = client.get("/monzo-callback", params={"code": "code", "state": "bad"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OAuth state"


def test_monzo_callback_requires_both_credentials(settings):
    settings = settings.__class__(
        settings.monzo_client_id, "", settings.monzo_redirect_uri
    )
    with _client_for_settings(settings) as client:
        client.app.state.oauth_states.add("valid")
        response = client.get(
            "/monzo-callback", params={"code": "code", "state": "valid"}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Monzo OAuth is not configured"


def test_monzo_callback_requires_jwt_configuration(settings):
    incomplete_settings = replace(settings, jwt_secret_key="")
    with _client_for_settings(incomplete_settings) as client:
        client.app.state.oauth_states.add("valid")
        response = client.get(
            "/monzo-callback", params={"code": "code", "state": "valid"}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Session signing is not configured"


@pytest.mark.parametrize("token_response", [{}, {"user_id": "user-1"}])
def test_monzo_callback_rejects_incomplete_token_payload(
    monkeypatch, client, token_response
):
    async def fake_exchange(code, settings):
        return token_response

    monkeypatch.setattr(monzo, "exchange_authorization_code", fake_exchange)
    client.app.state.oauth_states.add("valid")
    response = client.get(
        "/monzo-callback", params={"code": "code", "state": "valid"}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Monzo returned an invalid token response"


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_detail"),
    [
        (
            httpx.HTTPStatusError(
                "bad response",
                request=httpx.Request("POST", "https://api.monzo.com/oauth2/token"),
                response=httpx.Response(422),
            ),
            422,
            "Monzo token exchange failed",
        ),
        (
            httpx.ConnectError("offline"),
            503,
            "Monzo API is unreachable",
        ),
    ],
)
def test_monzo_callback_maps_upstream_errors(
    monkeypatch, client, failure, expected_status, expected_detail
):
    async def fail_exchange(code, settings):
        raise failure

    monkeypatch.setattr(monzo, "exchange_authorization_code", fail_exchange)
    client.app.state.oauth_states.add("valid")

    response = client.get("/monzo-callback", params={"code": "code", "state": "valid"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert "valid" not in client.app.state.oauth_states

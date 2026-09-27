import httpx
import pytest
from datetime import datetime, timezone
from dataclasses import replace

from app.routers import monzo, tasks


def test_health_route(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"message": "ok"}


def test_create_task_calls_scheduler_service(monkeypatch, client):
    job = type("Job", (), {"id": "job-123"})()
    scheduled_for = datetime(2030, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    called = {}

    def fake_schedule(scheduler, message):
        called.update(scheduler=scheduler, message=message)
        return job, scheduled_for

    monkeypatch.setattr(tasks, "schedule_message", fake_schedule)
    response = client.post("/create-task", params={"msg": "deposit"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "job_id": "job-123",
        "scheduled_for": scheduled_for.isoformat(),
    }
    assert called["scheduler"] is client.app.state.scheduler
    assert called["message"] == "deposit"


def test_create_task_uses_default_message(monkeypatch, client):
    monkeypatch.setattr(
        tasks,
        "schedule_message",
        lambda scheduler, message: (
            type("Job", (), {"id": "job"})(),
            datetime(2030, 1, 1, tzinfo=timezone.utc),
        ),
    )

    response = client.post("/create-task")

    assert response.status_code == 200
    assert response.json()["scheduled_for"] == "2030-01-01T00:00:00+00:00"


def test_monzo_redirect_requires_client_id(settings):
    settings = settings.__class__("", settings.monzo_client_secret, settings.monzo_redirect_uri)
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        response = client.get("/monzo-redirect")

    assert response.status_code == 503
    assert response.json()["detail"] == "Monzo OAuth is not configured"


def test_monzo_callback_rejects_unknown_state(client):
    response = client.get("/monzo-callback", params={"code": "code", "state": "bad"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OAuth state"


def test_monzo_callback_requires_both_credentials(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app

    settings = settings.__class__(settings.monzo_client_id, "", settings.monzo_redirect_uri)
    with TestClient(create_app(settings)) as client:
        client.app.state.oauth_states.add("valid")
        response = client.get("/monzo-callback", params={"code": "code", "state": "valid"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Monzo OAuth is not configured"


def test_monzo_callback_requires_jwt_configuration(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app

    incomplete_settings = replace(settings, jwt_secret_key="")
    with TestClient(create_app(incomplete_settings)) as client:
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
def test_monzo_callback_maps_upstream_errors(monkeypatch, client, failure, expected_status, expected_detail):
    async def fail_exchange(code, settings):
        raise failure

    monkeypatch.setattr(monzo, "exchange_authorization_code", fail_exchange)
    client.app.state.oauth_states.add("valid")

    response = client.get("/monzo-callback", params={"code": "code", "state": "valid"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert "valid" not in client.app.state.oauth_states

import traceback
import pytest
from pydantic import ValidationError
from app.schemas.monzo import MonzoTokenResponse


@pytest.mark.parametrize(
    "body",
    [
        {"refreshToke": "SYNTHETIC_SECRET_" + "x" * 48},
        {"SYNTHETIC_SECRET_FIELD": "x" * 64},
        {"refreshToken": "short-secret"},
    ],
)
def test_validation_errors_do_not_return_submitted_secrets(client, body):
    response = client.post("/auth/refresh", json=body)
    assert response.status_code == 422
    for key, value in body.items():
        assert value not in response.text
        if key.startswith("SYNTHETIC"):
            assert key not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_upstream_validation_tracebacks_hide_token_inputs():
    payload = {
        "access_token": "UPSTREAM_SYNTHETIC_SECRET",
        "refresh_token": "UPSTREAM_REFRESH_SECRET",
        "expires_in": 60,
    }
    with pytest.raises(ValidationError) as caught:
        MonzoTokenResponse.model_validate(payload)
    text = "".join(traceback.format_exception(caught.value))
    assert "UPSTREAM" not in text
    assert "input_value" not in text


def test_private_responses_and_errors_are_not_cacheable(client):
    response = client.get("/balance", params={"account_id": "acc_test"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"

from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import respx
from fastapi.testclient import TestClient

from app.db.models import MonzoCredential
from app.services.token_store import decrypt_token


def test_oauth_state_is_bound_to_the_browser_cookie(client):
    redirect = client.get("/monzo-redirect", follow_redirects=False)
    state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]

    other_browser = TestClient(client.app)
    callback = other_browser.get(
        "/monzo-callback", params={"code": "authorization-code", "state": state}
    )
    other_browser.close()

    assert callback.status_code == 400
    assert state in client.app.state.oauth_states


def test_oauth_redirect_and_token_exchange_happy_path(client, settings):
    with respx.mock(assert_all_called=True) as monzo_mock:
        token_route = monzo_mock.post("https://api.monzo.com/oauth2/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "test-access-token",
                    "refresh_token": "test-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 21600,
                    "user_id": "user_test123",
                },
            )
        )
        redirect = client.get("/monzo-redirect", follow_redirects=False)
        assert redirect.status_code == 302

        redirect_url = urlparse(redirect.headers["location"])
        redirect_params = parse_qs(redirect_url.query)
        assert redirect_url.scheme == "https"
        assert redirect_url.netloc == "auth.monzo.com"
        assert redirect_params["client_id"] == [settings.monzo_client_id]
        assert redirect_params["redirect_uri"] == [settings.monzo_redirect_uri]
        assert redirect_params["response_type"] == ["code"]
        state = redirect_params["state"][0]
        assert state in client.app.state.oauth_states
        cookie = redirect.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Max-Age=600" in cookie

        callback = client.get(
            "/monzo-callback", params={"code": "authorization-code", "state": state}
        )

    assert callback.status_code == 200
    response_body = callback.json()
    assert response_body["expiresIn"] == 900
    assert 'monzo_oauth_state="";' in callback.headers["set-cookie"]
    assert state not in client.app.state.oauth_states
    jwt_claims = jwt.decode(
        response_body["token"], settings.jwt_secret_key, algorithms=["HS256"]
    )
    assert jwt_claims["sub"] == "user_test123"
    assert "access_token" not in callback.text

    with client.app.state.session_factory() as session:
        credential = session.get(MonzoCredential, "user_test123")
        assert credential is not None
        assert decrypt_token(credential.access_token, settings) == "test-access-token"
        assert decrypt_token(credential.refresh_token, settings) == "test-refresh-token"

    assert token_route.called
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form == {
        "grant_type": ["authorization_code"],
        "client_id": [settings.monzo_client_id],
        "client_secret": [settings.monzo_client_secret],
        "redirect_uri": [settings.monzo_redirect_uri],
        "code": ["authorization-code"],
    }

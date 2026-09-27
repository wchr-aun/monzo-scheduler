from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import respx

from app.db.models import MonzoCredential


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

        callback = client.get(
            "/monzo-callback", params={"code": "authorization-code", "state": state}
        )

    assert callback.status_code == 200
    assert callback.json() == {"message": "Monzo account connected"}
    set_cookie = callback.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "max-age=86400" in set_cookie
    assert state not in client.app.state.oauth_states
    cookie = client.cookies.get("session")
    assert cookie
    jwt_claims = jwt.decode(cookie, settings.jwt_secret_key, algorithms=["HS256"])
    assert jwt_claims["sub"] == "user_test123"
    assert "access_token" not in callback.text

    with client.app.state.session_factory() as session:
        credential = session.get(MonzoCredential, "user_test123")
        assert credential is not None
        assert credential.access_token == "test-access-token"
        assert credential.refresh_token == "test-refresh-token"

    assert token_route.called
    form = parse_qs(token_route.calls.last.request.content.decode())
    assert form == {
        "grant_type": ["authorization_code"],
        "client_id": [settings.monzo_client_id],
        "client_secret": [settings.monzo_client_secret],
        "redirect_uri": [settings.monzo_redirect_uri],
        "code": ["authorization-code"],
    }

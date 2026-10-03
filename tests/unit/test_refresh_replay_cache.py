from app.services.refresh_replay import RefreshReplayCache


def test_cache_is_bounded_and_only_returns_matching_latest_rotation(monkeypatch):
    monkeypatch.setattr("app.services.refresh_replay.MAX_CACHED_REFRESH_RESPONSES", 2)
    monkeypatch.setattr("app.services.refresh_replay.monotonic", lambda: 100.0)
    cache = RefreshReplayCache()
    for session_id in ("a", "b", "c"):
        cache.record(session_id, "previous", "current", session_id, 5)
    assert cache.lookup("a", "previous", "current") is None
    assert cache.lookup("b", "previous", "current") == "b"
    assert cache.lookup("c", "previous", "current") == "c"
    assert cache.lookup("c", "older", "current") is None
    assert cache.lookup("c", "previous", "newer") is None
    cache.discard("c")
    assert cache.lookup("c", "previous", "current") is None


def test_short_access_token_lifetime_limits_replay(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.services.refresh_replay.monotonic", lambda: clock[0])
    cache = RefreshReplayCache()
    cache.record("a", "previous", "current", "pair", 1)
    assert cache.lookup("a", "previous", "current") == "pair"
    clock[0] += 1
    assert cache.lookup("a", "previous", "current") is None

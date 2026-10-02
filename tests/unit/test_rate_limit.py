from app.rate_limit import RequestRateLimiter


def test_rate_limiter_rejects_over_limit_and_expires_old_requests():
    limiter = RequestRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.allow("client", now=0)
    assert limiter.allow("client", now=1)
    assert not limiter.allow("client", now=2)
    assert limiter.allow("client", now=10)

import asyncio
from app.request_bounds import RequestBoundsMiddleware


def test_oversized_stream_is_rejected_without_content_length():
    async def scenario():
        called = False
        messages = iter(
            [
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"456", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        async def app(*args):
            nonlocal called
            called = True

        middleware = RequestBoundsMiddleware(app, max_body_bytes=5)
        await middleware({"type": "http", "headers": []}, receive, send)
        assert sent[0]["status"] == 413
        assert not called
        assert middleware.active == 0

    asyncio.run(scenario())


def test_concurrency_limit_and_disconnect_release_capacity():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        sent = []

        async def app(*args):
            entered.set()
            await release.wait()

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)

        middleware = RequestBoundsMiddleware(app, max_concurrent_requests=1)
        task = asyncio.create_task(
            middleware({"type": "http", "headers": []}, receive, send)
        )
        await entered.wait()
        await middleware({"type": "http", "headers": []}, receive, send)
        assert sent[0]["status"] == 503
        release.set()
        await task
        assert middleware.active == 0

    asyncio.run(scenario())


def test_slow_body_times_out_and_releases_capacity():
    async def scenario():
        sent = []

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)

        async def app(*args):
            raise AssertionError("timed out request reached routes")

        middleware = RequestBoundsMiddleware(app, body_timeout_seconds=0.01)
        await middleware({"type": "http", "headers": []}, receive, send)
        assert sent[0]["status"] == 408
        assert middleware.active == 0

    asyncio.run(scenario())


def test_declared_large_body_is_rejected(client):
    assert client.post("/auth/refresh", content=b"x" * 16385).status_code == 413

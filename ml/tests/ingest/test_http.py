import httpx

from shortlist_ml.ingest.http import Fetcher, RateLimiter


def test_rate_limiter_spaces_requests_per_host() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(1.0, clock=lambda: now[0], sleep=sleep)
    limiter.wait("a.test")  # first call never waits
    now[0] += 0.25
    limiter.wait("a.test")  # 0.75s short of the 1s interval
    limiter.wait("b.test")  # different host: independent
    assert slept == [0.75]


def _fetcher(handler, sleeps: list[float]) -> Fetcher:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, RateLimiter(0.0, sleep=lambda _s: None), sleep=sleeps.append)


def test_retries_5xx_then_succeeds() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(503 if len(calls) < 3 else 200, content=b"[]")

    sleeps: list[float] = []
    res = _fetcher(handler, sleeps).get("https://x.test/a")
    assert res.status_code == 200 and len(calls) == 3 and sleeps == [2.0, 4.0]


def test_gives_up_after_max_retries() -> None:
    res = _fetcher(lambda r: httpx.Response(500), []).get("https://x.test/a")
    assert res.status_code == 500


def test_404_is_not_retried() -> None:
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    res = _fetcher(handler, []).get("https://x.test/a")
    assert res.status_code == 404 and len(calls) == 1


def test_429_honours_retry_after_once_then_gives_up() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "7"})

    sleeps: list[float] = []
    res = _fetcher(handler, sleeps).get("https://x.test/a")
    assert res.status_code == 429 and len(calls) == 2 and sleeps == [7.0]  # never loops on 429


def test_transport_error_returns_status_zero() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    res = _fetcher(handler, []).get("https://x.test/a")
    assert res.status_code == 0 and res.error == "ConnectError"

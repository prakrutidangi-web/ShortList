"""Polite HTTP: per-host rate limiting, bounded retries, no attempt to evade limits."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

MAX_RETRY_AFTER_S = 60.0


class RateLimiter:
    """Enforces a minimum interval between requests to the same host."""

    def __init__(
        self,
        interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval_s = interval_s
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = self.interval_s - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int  # 0 means a transport error (no HTTP response)
    content: bytes
    error: str | None = None


class Fetcher:
    """GET with rate limiting. Retries 5xx/transport errors (2x, backoff). On 429 it honours
    Retry-After once (capped at 60s) and then gives up; it never hammers or evades a limit."""

    def __init__(
        self,
        client: httpx.Client,
        limiter: RateLimiter,
        *,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._limiter = limiter
        self._max_retries = max_retries
        self._sleep = sleep

    def get(self, url: str) -> FetchResult:
        host = urlparse(url).netloc
        attempt = 0
        retried_429 = False
        while True:
            self._limiter.wait(host)
            try:
                resp = self._client.get(url)
            except httpx.TransportError as exc:
                if attempt < self._max_retries:
                    attempt += 1
                    self._sleep(2.0**attempt)
                    continue
                return FetchResult(url, 0, b"", f"{type(exc).__name__}")
            if resp.status_code == 429 and not retried_429:
                retried_429 = True
                try:
                    delay = float(resp.headers.get("Retry-After", "5"))
                except ValueError:
                    delay = 5.0
                self._sleep(min(max(delay, 0.0), MAX_RETRY_AFTER_S))
                continue
            if resp.status_code >= 500 and attempt < self._max_retries:
                attempt += 1
                self._sleep(2.0**attempt)
                continue
            return FetchResult(url, resp.status_code, resp.content)


def make_client(user_agent: str) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )

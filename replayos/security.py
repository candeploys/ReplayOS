from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
import time

from .config import AuthConfig


@dataclass(frozen=True)
class AuthResult:
    allowed: bool
    reason: str | None = None


class APIKeyAuth:
    def __init__(self, config: AuthConfig):
        self._config = config
        self._keys = set(config.api_keys)

    def validate(self, header_token: str | None, client_ip: str) -> AuthResult:
        if not self._config.require_api_key:
            return AuthResult(allowed=True)

        if self._config.allow_localhost_without_key and client_ip in {"127.0.0.1", "::1", "localhost"}:
            return AuthResult(allowed=True)

        token = (header_token or "").strip()
        if not token:
            return AuthResult(allowed=False, reason="missing_api_key")

        if token not in self._keys:
            return AuthResult(allowed=False, reason="invalid_api_key")

        return AuthResult(allowed=True)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            queue = self._hits.setdefault(key, deque())
            while queue and (now - queue[0]) > self.window_seconds:
                queue.popleft()

            if len(queue) >= self.max_requests:
                oldest = queue[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

            queue.append(now)
            return RateLimitResult(allowed=True)


def parse_api_key_from_headers(headers: dict[str, str]) -> str:
    auth_value = headers.get("Authorization", "").strip()
    if auth_value.lower().startswith("bearer "):
        return auth_value[7:].strip()

    x_api_key = headers.get("X-API-Key", "").strip()
    if x_api_key:
        return x_api_key
    return ""

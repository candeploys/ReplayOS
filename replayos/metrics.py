from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
import time


@dataclass(frozen=True)
class AlertSnapshot:
    active: bool
    error_rate: float
    threshold: float
    window_seconds: int
    total_requests: int
    error_requests: int


class MetricsStore:
    def __init__(self):
        self._lock = Lock()
        self._request_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_sum_ms: float = 0.0
        self._duration_count: int = 0
        self._provider_errors: int = 0
        self._status_window: deque[tuple[float, int]] = deque()

    def observe_request(self, method: str, path: str, status: int, duration_ms: float) -> None:
        status_str = str(status)
        with self._lock:
            self._request_counts[(method.upper(), path, status_str)] += 1
            self._duration_sum_ms += float(duration_ms)
            self._duration_count += 1
            self._status_window.append((time.time(), int(status)))

    def observe_provider_error(self) -> None:
        with self._lock:
            self._provider_errors += 1

    def _trim_window(self, window_seconds: int) -> None:
        cutoff = time.time() - window_seconds
        while self._status_window and self._status_window[0][0] < cutoff:
            self._status_window.popleft()

    def alert_snapshot(
        self,
        threshold: float,
        window_seconds: int,
        min_requests: int,
    ) -> AlertSnapshot:
        with self._lock:
            self._trim_window(window_seconds)
            total = len(self._status_window)
            errors = sum(1 for _, status in self._status_window if status >= 500)
            error_rate = (errors / total) if total else 0.0
            active = total >= min_requests and error_rate >= threshold
            return AlertSnapshot(
                active=active,
                error_rate=error_rate,
                threshold=threshold,
                window_seconds=window_seconds,
                total_requests=total,
                error_requests=errors,
            )

    def render_prometheus(
        self,
        threshold: float,
        window_seconds: int,
        min_requests: int,
    ) -> str:
        with self._lock:
            self._trim_window(window_seconds)
            lines: list[str] = []
            lines.append("# HELP replayos_http_requests_total Total HTTP requests")
            lines.append("# TYPE replayos_http_requests_total counter")
            for (method, path, status), count in sorted(self._request_counts.items()):
                labels = f'method="{_escape(method)}",path="{_escape(path)}",status="{_escape(status)}"'
                lines.append(f"replayos_http_requests_total{{{labels}}} {count}")

            lines.append("# HELP replayos_http_request_duration_ms_sum Sum of HTTP request durations in milliseconds")
            lines.append("# TYPE replayos_http_request_duration_ms_sum counter")
            lines.append(f"replayos_http_request_duration_ms_sum {self._duration_sum_ms:.6f}")

            lines.append("# HELP replayos_http_request_duration_ms_count Number of observed HTTP request durations")
            lines.append("# TYPE replayos_http_request_duration_ms_count counter")
            lines.append(f"replayos_http_request_duration_ms_count {self._duration_count}")

            lines.append("# HELP replayos_provider_errors_total Total provider errors")
            lines.append("# TYPE replayos_provider_errors_total counter")
            lines.append(f"replayos_provider_errors_total {self._provider_errors}")

            total = len(self._status_window)
            errors = sum(1 for _, status in self._status_window if status >= 500)
            error_rate = (errors / total) if total else 0.0
            active = 1 if total >= min_requests and error_rate >= threshold else 0

            lines.append("# HELP replayos_error_rate_window Current 5xx error rate over sliding window")
            lines.append("# TYPE replayos_error_rate_window gauge")
            lines.append(f"replayos_error_rate_window {error_rate:.6f}")

            lines.append("# HELP replayos_error_rate_threshold Configured error rate threshold")
            lines.append("# TYPE replayos_error_rate_threshold gauge")
            lines.append(f"replayos_error_rate_threshold {threshold:.6f}")

            lines.append("# HELP replayos_alert_active 1 when error-rate alert is active")
            lines.append("# TYPE replayos_alert_active gauge")
            lines.append(f"replayos_alert_active {active}")

            return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')

"""
Minimal in-process metrics. No Prometheus server, no new dependency — just
enough to answer "how many requests, how slow, how many failures" and,
if anyone ever points a real Prometheus at GET /metrics (see app/main.py
for how that's gated), the text format below is directly scrapable.

Deliberately NO per-user/per-patient/per-clinic labels. A label on an
unbounded value (a user ID, an email, a clinic name) does two bad things
at once: it blows up cardinality in any real metrics backend, and it turns
the metrics endpoint into an accidental second, access-control-free audit
log. Labels here are small, fixed sets only: HTTP method, status class.
"""
import threading

_LabelKey = tuple[str, ...]


class _Counter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[_LabelKey, float] = {}

    def inc(self, *labels: str, amount: float = 1.0) -> None:
        with self._lock:
            self._values[labels] = self._values.get(labels, 0.0) + amount

    def snapshot(self) -> dict[_LabelKey, float]:
        with self._lock:
            return dict(self._values)


http_requests_total = _Counter()  # labels: (method, status_class)
http_request_duration_seconds_sum = _Counter()  # labels: (method,)
http_request_duration_seconds_count = _Counter()  # labels: (method,)
auth_failures_total = _Counter()  # no labels
rate_limit_events_total = _Counter()  # no labels
db_errors_total = _Counter()  # no labels


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def _render(name: str, counter: _Counter, label_names: tuple[str, ...]) -> list[str]:
    lines = [f"# TYPE {name} counter"]
    for labels, value in sorted(counter.snapshot().items()):
        if label_names:
            label_str = ",".join(f'{k}="{v}"' for k, v in zip(label_names, labels, strict=True))
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")
    return lines


def render_prometheus_text() -> str:
    lines: list[str] = []
    lines += _render("myvita_http_requests_total", http_requests_total, ("method", "status_class"))
    lines += _render(
        "myvita_http_request_duration_seconds_sum", http_request_duration_seconds_sum, ("method",)
    )
    lines += _render(
        "myvita_http_request_duration_seconds_count", http_request_duration_seconds_count, ("method",)
    )
    lines += _render("myvita_auth_failures_total", auth_failures_total, ())
    lines += _render("myvita_rate_limit_events_total", rate_limit_events_total, ())
    lines += _render("myvita_db_errors_total", db_errors_total, ())
    return "\n".join(lines) + "\n"

"""Prometheus-метрики сервиса."""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

webhooks_total = Counter("ai_developer_webhooks_total", "Принятые вебхуки", ["source", "outcome"])
phase_errors_total = Counter(
    "ai_developer_phase_errors_total", "Ошибки фаз", ["phase", "error_type"]
)
go_decisions_total = Counter("ai_developer_go_decisions_total", "Решения по /go", ["decision"])
phase_duration_seconds = Histogram(
    "ai_developer_phase_duration_seconds", "Длительность фаз", ["phase"]
)


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST

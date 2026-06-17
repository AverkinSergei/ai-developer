"""Preview deploy / smoke-тесты, если поддерживается репозиторием.

Гейтинг: preview нужен при явном флаге preview=yes или для high-risk изменений
во frontend/API/integration. Реальный деплой подключается на интеграции.
"""

from app.config import Settings
from app.contracts import RiskPlanGate, TaskCard

_PREVIEW_AREAS = {"frontend", "api", "integration"}


def preview_required(card: TaskCard, gate: RiskPlanGate, settings: Settings) -> bool:
    if card.preview is True:
        return True
    if not settings.preview_enabled:
        return False
    areas = {a.lower() for a in card.affected_area}
    return gate.risk_level == "high" and bool(areas & _PREVIEW_AREAS)


async def run_smoke(preview_url: str) -> bool:
    """Заглушка smoke-проверки. Реальные проверки подключаются на интеграции."""
    return True

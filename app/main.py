"""FastAPI-приложение: вебхуки, health/readiness, служебные endpoint'ы.

Тяжёлая работа выполняется в фоне (worker), endpoint'ы только валидируют и
быстро отвечают.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from app import __version__, metrics
from app.audit import configure_logging
from app.config import settings
from app.db.base import sessionmanager
from app.state import store
from app.webhooks import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    sessionmanager.init(settings.briefing_db_url)
    store.init()
    yield
    await store.close()
    await sessionmanager.close()


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.include_router(webhooks_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404)
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Проверка связности с Redis и БД."""
    checks: dict[str, bool] = {}
    try:
        checks["redis"] = await store.ping()
    except Exception:
        checks["redis"] = False
    try:
        async with sessionmanager.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        checks["db"] = True
    except Exception:
        checks["db"] = False

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "checks": checks},
    )

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.api.memories import router as memories_router
from app.core.config import get_settings
from app.core.deps import shutdown_memory_client
from app.core.logging import configure_logging
from app.db.session import engine, get_db

configure_logging(get_settings())

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log.error("startup.db_unreachable", error=str(exc))
        raise RuntimeError("Database unreachable on startup; aborting") from exc
    log.info("startup.db_ok")
    yield
    shutdown_memory_client()
    engine.dispose()


app = FastAPI(title="Me", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(memories_router)


@app.get("/healthz")
def healthz(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.warning("healthz.db_unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error"},
        )
    return JSONResponse(status_code=200, content={"status": "ok", "db": "ok"})

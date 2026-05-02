from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging(get_settings())

app = FastAPI(title="Me")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

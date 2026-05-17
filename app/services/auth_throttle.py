from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.auth_throttle import AuthThrottle


def throttle_key(action: str, client_ip: str) -> str:
    return f"{action}:{client_ip}"


def get_lock_expiry(
    db: Session,
    *,
    action: str,
    client_ip: str,
    now: datetime,
) -> datetime | None:
    row = db.get(AuthThrottle, throttle_key(action, client_ip))
    if row is None or row.locked_until is None or row.locked_until <= now:
        return None
    return row.locked_until


def record_failure(
    db: Session,
    *,
    action: str,
    client_ip: str,
    now: datetime,
    settings: Settings,
) -> datetime | None:
    key = throttle_key(action, client_ip)
    row = db.get(AuthThrottle, key)

    window = timedelta(seconds=settings.auth_rate_limit_window_seconds)
    lock = timedelta(seconds=settings.auth_rate_limit_lock_seconds)

    if row is None:
        row = AuthThrottle(
            key=key,
            action=action,
            client_ip=client_ip,
            failure_count=1,
            window_started_at=now,
            locked_until=None,
        )
        db.add(row)
    else:
        if (row.locked_until is not None and row.locked_until <= now) or (
            row.window_started_at + window <= now
        ):
            row.failure_count = 1
            row.window_started_at = now
            row.locked_until = None
        else:
            row.failure_count += 1

    if row.failure_count >= settings.auth_rate_limit_failures:
        row.locked_until = now + lock

    db.commit()
    return row.locked_until


def clear_failures(
    db: Session,
    *,
    action: str,
    client_ip: str,
) -> None:
    row = db.get(AuthThrottle, throttle_key(action, client_ip))
    if row is None:
        return
    db.delete(row)
    db.commit()

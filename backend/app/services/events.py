from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.timezone import utc_now
from app.models import SystemEvent


def record_event(
    db: Session,
    *,
    event_type: str,
    severity: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> SystemEvent:
    event = SystemEvent(
        timestamp_utc=utc_now(),
        event_type=event_type,
        severity=severity,
        message=message,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event

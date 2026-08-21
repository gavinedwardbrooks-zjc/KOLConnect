"""Compatibility helpers for UUID features that vary by Python version."""

from __future__ import annotations

import uuid


def uuid7_or_uuid4() -> uuid.UUID:
    """Return UUID7 when the runtime provides it, otherwise a unique UUID4."""
    uuid7 = getattr(uuid, "uuid7", None)
    if callable(uuid7):
        return uuid7()
    return uuid.uuid4()

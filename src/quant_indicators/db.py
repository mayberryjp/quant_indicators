"""Database engine construction.

Every engine pins the Postgres session time zone to the container's local zone
so all ``timestamptz`` values are stored and returned in the container's local
time (New York) rather than UTC. Database functions like ``now()`` therefore
operate against the container's local clock and no other offset.
"""

from __future__ import annotations

import os
from typing import Any


def local_timezone() -> str:
    """Return the container's local IANA time zone used for all DB sessions."""
    return os.environ.get("TZ", "").strip() or "America/New_York"


def timezone_connect_args() -> dict[str, str]:
    """psycopg connect options that pin the session time zone to the local zone."""
    return {"options": f"-c timezone={local_timezone()}"}


def create_engine(url: str, **kwargs: Any) -> Any:
    """Create a SQLAlchemy engine with the session time zone pinned locally."""
    from sqlalchemy import create_engine as _create_engine

    connect_args = {**timezone_connect_args(), **kwargs.pop("connect_args", {})}
    return _create_engine(url, connect_args=connect_args, **kwargs)

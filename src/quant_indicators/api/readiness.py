"""Database readiness checks for the API.

The API exposes a /ready endpoint that verifies the database is migrated to the
expected schema version before reporting healthy. Connection errors are
sanitized so credentials never leak into responses or logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from quant_indicators._cli_impl import EXPECTED_SCHEMA_VERSION, EXPECTED_TABLES


@dataclass(frozen=True)
class ReadinessStatus:
    ready: bool
    schema_version: str | None = None
    expected_version: str = EXPECTED_SCHEMA_VERSION
    tables_present: int = 0
    tables_expected: int = len(EXPECTED_TABLES)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ready": self.ready,
            "schema_version": self.schema_version,
            "expected_version": self.expected_version,
            "tables_present": self.tables_present,
            "tables_expected": self.tables_expected,
        }
        if self.error:
            payload["error"] = self.error
        return payload


_URL_CREDENTIALS = re.compile(r"//[^/@\s]*@")


def sanitize_readiness_error(message: str) -> str:
    """Redact credentials embedded in connection URLs before surfacing errors."""
    return _URL_CREDENTIALS.sub("//***@", message)


def check_database_readiness(engine: Engine) -> ReadinessStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            schema_version = connection.execute(
                text("SELECT version_num FROM indicators.alembic_version_indicators")
            ).scalar_one()
            tables = connection.execute(
                text("""
                    SELECT count(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'indicators'
                      AND table_type = 'BASE TABLE'
                      AND table_name = ANY(:names)
                """),
                {"names": list(EXPECTED_TABLES)},
            ).scalar_one()
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        return ReadinessStatus(
            ready=False,
            error=sanitize_readiness_error(str(exc)),
        )

    ready = schema_version == EXPECTED_SCHEMA_VERSION and tables == len(EXPECTED_TABLES)
    return ReadinessStatus(
        ready=ready,
        schema_version=schema_version,
        tables_present=tables,
    )

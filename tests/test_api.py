"""Tests for the retrieval API using an injected fake engine and stubbed data layer."""

from __future__ import annotations

import json

import pytest
import webtest

import quant_indicators.api.app as app_module
from quant_indicators.api.readiness import ReadinessStatus


class _FakeEngine:
    """Stand-in for a SQLAlchemy engine; only dispose() is exercised."""

    disposed = False

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "check_database_readiness",
        lambda engine: ReadinessStatus(
            ready=True, schema_version="0001_indicators_schema", tables_present=3
        ),
    )
    monkeypatch.setattr(
        app_module.data,
        "list_indicator_definitions",
        lambda engine, active_only=True: [
            {"code": "sma_50", "version": "1", "display_name": "SMA (50)", "active": True,
             "input_series": "close", "outputs": [], "params": {"period": 50},
             "min_periods": 50, "description": "50d SMA"}
        ],
    )
    monkeypatch.setattr(
        app_module.data,
        "list_indicator_values",
        lambda engine, query: [
            {"ticker": "AAPL", "symbol_id": 1, "bar_date": "2024-03-01",
             "indicator_code": "sma_50", "indicator_version": "1",
             "adjustment_type": "unadjusted", "value": 150.0, "values": None}
        ],
    )
    monkeypatch.setattr(
        app_module.data,
        "latest_values_for_ticker",
        lambda engine, ticker, adjustment_type=None: [
            {"ticker": ticker.upper(), "symbol_id": 1, "bar_date": "2024-03-01",
             "indicator_code": "sma_50", "indicator_version": "1",
             "adjustment_type": "unadjusted", "value": 150.0, "values": None}
        ],
    )
    monkeypatch.setattr(
        app_module.data,
        "coverage",
        lambda engine, ticker=None: [
            {"ticker": "AAPL", "indicator_code": "sma_50", "points": 10,
             "first_date": "2024-01-01", "last_date": "2024-03-01"}
        ],
    )
    monkeypatch.setattr(
        app_module.data,
        "list_runs",
        lambda engine, limit=50: [{"id": 1, "status": "completed"}],
    )
    monkeypatch.setattr(
        app_module.data,
        "latest_run",
        lambda engine: {"id": 1, "status": "completed"},
    )
    monkeypatch.setattr(
        app_module.data,
        "get_run",
        lambda engine, run_id: {"id": run_id, "status": "completed"} if run_id == 1 else None,
    )

    app = app_module.create_app(engine_factory=_FakeEngine)
    return webtest.TestApp(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_ready(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json["ready"] is True
    assert resp.json["schema_version"] == "0001_indicators_schema"


def test_list_indicators(client):
    resp = client.get("/indicators")
    assert resp.status_code == 200
    assert resp.json["count"] == 1
    assert resp.json["indicators"][0]["code"] == "sma_50"


def test_indicator_values(client):
    resp = client.get("/indicators/values?ticker=AAPL&indicator=sma_50")
    assert resp.status_code == 200
    assert resp.json["values"][0]["value"] == 150.0


def test_indicator_values_bad_date(client):
    resp = client.get("/indicators/values?from=not-a-date", expect_errors=True)
    assert resp.status_code == 400
    assert "invalid from" in resp.json["error"]


def test_latest_values(client):
    resp = client.get("/indicators/values/latest/aapl")
    assert resp.status_code == 200
    assert resp.json["ticker"] == "AAPL"
    assert resp.json["count"] == 1


def test_coverage(client):
    resp = client.get("/indicators/coverage")
    assert resp.status_code == 200
    assert resp.json["coverage"][0]["ticker"] == "AAPL"


def test_runs(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json["count"] == 1


def test_latest_run(client):
    resp = client.get("/runs/latest")
    assert resp.status_code == 200
    assert resp.json["id"] == 1


def test_run_detail_found(client):
    resp = client.get("/runs/1")
    assert resp.status_code == 200
    assert resp.json["id"] == 1


def test_run_detail_missing(client):
    resp = client.get("/runs/999", expect_errors=True)
    assert resp.status_code == 404

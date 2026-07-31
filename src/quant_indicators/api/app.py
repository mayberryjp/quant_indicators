"""Bottle application exposing the read-only indicators API.

The app is built through `create_app` so tests can inject a fake engine
factory. In production each request gets a fresh engine from the module-level
factory and disposes it afterwards, keeping connection handling simple and
avoiding leaks across the long-lived waitress worker.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any, Callable

import bottle
from bottle import Bottle, HTTPResponse, request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from quant_indicators.api import indicators as data
from quant_indicators.api.readiness import check_database_readiness

log = logging.getLogger(__name__)

EngineFactory = Callable[[], Engine]


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://quant:quant_dev_password@localhost:5432/quant",
    )


def _default_engine_factory() -> Engine:
    return create_engine(_database_url(), pool_pre_ping=True)


def _json(payload: Any, status: int = 200) -> HTTPResponse:
    body = json.dumps(payload, default=str)
    return HTTPResponse(body=body, status=status, headers={"Content-Type": "application/json"})


def _parse_date_param(name: str) -> date | None:
    raw = request.query.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise _ApiError(f"invalid {name}: {raw} (use YYYY-MM-DD)", 400)


def _parse_int_param(name: str, default: int) -> int:
    raw = request.query.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise _ApiError(f"invalid {name}: {raw}", 400)


class _ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def create_app(engine_factory: EngineFactory | None = None) -> Bottle:
    app = Bottle()
    factory = engine_factory or _default_engine_factory

    def _with_engine(fn: Callable[[Engine], Any]) -> Any:
        engine = factory()
        try:
            return fn(engine)
        finally:
            engine.dispose()

    def _error_plugin(callback: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return callback(*args, **kwargs)
            except _ApiError as exc:
                return _json({"error": exc.message}, status=exc.status)
        return wrapper

    app.install(_error_plugin)

    @app.error(404)
    def _handle_404(err: bottle.HTTPError) -> str:  # noqa: ARG001
        bottle.response.content_type = "application/json"
        return json.dumps({"error": "not found"})

    @app.route("/health")
    def health() -> HTTPResponse:
        return _json({"status": "ok"})

    @app.route("/ready")
    def ready() -> HTTPResponse:
        status = _with_engine(check_database_readiness)
        return _json(status.as_dict(), status=200 if status.ready else 503)

    @app.route("/indicators")
    def indicators_list() -> HTTPResponse:
        active_only = request.query.get("active", "true").lower() != "false"
        rows = _with_engine(lambda e: data.list_indicator_definitions(e, active_only=active_only))
        return _json({"indicators": rows, "count": len(rows)})

    @app.route("/indicators/values")
    def indicator_values() -> HTTPResponse:
        query = data.ValuesQuery(
            ticker=request.query.get("ticker") or None,
            indicator_code=request.query.get("indicator") or None,
            adjustment_type=request.query.get("adjustment_type") or None,
            from_date=_parse_date_param("from"),
            to_date=_parse_date_param("to"),
            limit=_parse_int_param("limit", 500),
            offset=_parse_int_param("offset", 0),
        )
        rows = _with_engine(lambda e: data.list_indicator_values(e, query))
        return _json({"values": rows, "count": len(rows)})

    @app.route("/indicators/values/latest/<ticker>")
    def latest_values(ticker: str) -> HTTPResponse:
        adjustment_type = request.query.get("adjustment_type") or None
        rows = _with_engine(
            lambda e: data.latest_values_for_ticker(e, ticker, adjustment_type=adjustment_type)
        )
        if not rows:
            return _json({"ticker": ticker.upper(), "values": [], "count": 0}, status=404)
        return _json({"ticker": ticker.upper(), "values": rows, "count": len(rows)})

    @app.route("/indicators/coverage")
    def indicator_coverage() -> HTTPResponse:
        ticker = request.query.get("ticker") or None
        rows = _with_engine(lambda e: data.coverage(e, ticker=ticker))
        return _json({"coverage": rows, "count": len(rows)})

    @app.route("/runs")
    def runs() -> HTTPResponse:
        limit = _parse_int_param("limit", 50)
        rows = _with_engine(lambda e: data.list_runs(e, limit=limit))
        return _json({"runs": rows, "count": len(rows)})

    @app.route("/runs/latest")
    def latest_run() -> HTTPResponse:
        row = _with_engine(data.latest_run)
        if row is None:
            return _json({"error": "no runs found"}, status=404)
        return _json(row)

    @app.route("/runs/<run_id:int>")
    def run_detail(run_id: int) -> HTTPResponse:
        row = _with_engine(lambda e: data.get_run(e, run_id))
        if row is None:
            return _json({"error": f"run {run_id} not found"}, status=404)
        return _json(row)

    @app.hook("after_request")
    def _log_request() -> None:
        log.info("%s %s -> %s", request.method, request.path, bottle.response.status_code)

    return app


def serve() -> None:
    from waitress import serve as waitress_serve

    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    host = os.environ.get("API_LISTEN_ADDRESS", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8000"))
    app = create_app()
    log.info("serving quant_indicators API on %s:%d", host, port)
    waitress_serve(app, host=host, port=port)


if __name__ == "__main__":
    serve()

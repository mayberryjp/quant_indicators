"""Indicator computation job.

Reads daily bars from Postgres, runs the enabled set of registered indicators
per symbol, and upserts results into indicators.indicator_values with
idempotent ON CONFLICT semantics and per-run tracking.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from quant_indicators.bars.models import Bar, SymbolBars
from quant_indicators.bars.source import list_symbols_with_bars, load_symbol_bars
from quant_indicators.compute.summary import ComputeSummary
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import get_indicators

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComputeOptions:
    """Parameters for an indicator computation run."""

    from_date: date | None = None
    to_date: date | None = None
    tickers: list[str] | None = None
    adjustment_type: str = "unadjusted"
    indicator_codes: list[str] | None = None  # None => all registered
    mode: str = "backfill"  # 'backfill' or 'incremental'
    lookback_days: int = 400
    fixture_path: str | None = None
    dry_run: bool = False


UPSERT_INDICATOR_VALUE = text("""
    INSERT INTO indicators.indicator_values (
        symbol_id, ticker, bar_date, indicator_code, indicator_version,
        adjustment_type, value, values_json, indicator_run_id, updated_at
    ) VALUES (
        :symbol_id, :ticker, :bar_date, :indicator_code, :indicator_version,
        :adjustment_type, :value, CAST(:values_json AS JSON), :indicator_run_id, now()
    )
    ON CONFLICT (symbol_id, bar_date, indicator_code, indicator_version, adjustment_type)
    DO UPDATE SET
        ticker = EXCLUDED.ticker,
        value = EXCLUDED.value,
        values_json = EXCLUDED.values_json,
        indicator_run_id = EXCLUDED.indicator_run_id,
        updated_at = now()
""")

UPSERT_DEFINITION = text("""
    INSERT INTO indicators.indicator_definitions (
        code, version, display_name, active, input_series,
        outputs, params, min_periods, description, updated_at
    ) VALUES (
        :code, :version, :display_name, true, :input_series,
        CAST(:outputs AS JSON), CAST(:params AS JSON), :min_periods, :description, now()
    )
    ON CONFLICT (code, version)
    DO UPDATE SET
        display_name = EXCLUDED.display_name,
        active = true,
        input_series = EXCLUDED.input_series,
        outputs = EXCLUDED.outputs,
        params = EXCLUDED.params,
        min_periods = EXCLUDED.min_periods,
        description = EXCLUDED.description,
        updated_at = now()
""")


class IndicatorComputeJob:
    """Orchestrates indicator computation from Postgres bars into Postgres."""

    def __init__(self, *, engine: Engine | None = None, indicators: Sequence[Indicator] | None = None) -> None:
        self._engine = engine
        self._indicators = list(indicators) if indicators is not None else None

    def _resolve_indicators(self, options: ComputeOptions) -> list[Indicator]:
        if self._indicators is not None:
            return self._indicators
        return get_indicators(options.indicator_codes)

    # ── definitions ──────────────────────────────────────────────────────────

    def sync_definitions(self, indicators: Sequence[Indicator] | None = None) -> int:
        """Upsert indicator metadata from the registry into the database."""
        if self._engine is None:
            raise RuntimeError("Database engine is required to sync definitions")
        specs = [ind.spec() for ind in (indicators if indicators is not None else get_indicators())]
        with self._engine.begin() as conn:
            for spec in specs:
                conn.execute(
                    UPSERT_DEFINITION,
                    {
                        "code": spec.code,
                        "version": spec.version,
                        "display_name": spec.display_name,
                        "input_series": spec.input_series,
                        "outputs": json.dumps(spec.outputs),
                        "params": json.dumps(spec.params),
                        "min_periods": spec.min_periods,
                        "description": spec.description,
                    },
                )
        return len(specs)

    # ── run ──────────────────────────────────────────────────────────────────

    def run(self, options: ComputeOptions) -> ComputeSummary:
        started = time.monotonic()
        summary = ComputeSummary(mode=options.mode)

        if options.fixture_path:
            return self._run_fixture(options, summary, started)

        if self._engine is None:
            raise RuntimeError("Database engine is required for computation")

        indicators = self._resolve_indicators(options)
        summary.indicators_run = len(indicators)

        # Keep the registry-backed metadata current before writing values.
        try:
            self.sync_definitions(indicators)
        except Exception as exc:  # noqa: BLE001 - definition sync must not abort a run
            log.warning("definition sync failed: %s", exc)
            summary.warnings.append(f"definition sync failed: {exc}")

        targets = list_symbols_with_bars(
            self._engine,
            adjustment_type=options.adjustment_type,
            tickers=options.tickers,
        )
        summary.symbols_requested = len(targets)
        if not targets:
            log.warning("no symbols with bars to compute")
            summary.duration_seconds = time.monotonic() - started
            return summary

        run_id = self._create_run(options, len(targets))
        summary.run_id = run_id

        load_start = None
        if options.from_date is not None:
            load_start = options.from_date - timedelta(days=options.lookback_days)

        for symbol_id, ticker in targets:
            try:
                symbol_bars = load_symbol_bars(
                    self._engine,
                    symbol_id=symbol_id,
                    ticker=ticker,
                    adjustment_type=options.adjustment_type,
                    start_date=load_start,
                    end_date=options.to_date,
                )
                upserted = self._compute_and_store(symbol_bars, indicators, options, run_id)
                summary.values_upserted += upserted
                summary.symbols_succeeded += 1
                if upserted == 0:
                    summary.warnings.append(f"{ticker}: no indicator values produced")
            except Exception as exc:  # noqa: BLE001 - isolate per-symbol failures
                summary.symbols_failed += 1
                summary.errors += 1
                summary.failures.append(f"{ticker}: {exc}")
                log.error("failed to compute indicators for %s: %s", ticker, exc, exc_info=True)
            self._heartbeat(run_id)

        summary.status = "failed" if summary.errors > 0 and summary.symbols_succeeded == 0 else "ok"
        summary.duration_seconds = time.monotonic() - started
        self._finalize_run(run_id, summary)
        return summary

    def _compute_and_store(
        self,
        symbol_bars: SymbolBars,
        indicators: Sequence[Indicator],
        options: ComputeOptions,
        run_id: int | None,
    ) -> int:
        rows = self._compute_rows(symbol_bars, indicators, options, run_id)
        if not rows or self._engine is None:
            return len(rows)
        with self._engine.begin() as conn:
            conn.execute(UPSERT_INDICATOR_VALUE, rows)
        log.info("upserted %d indicator values for %s", len(rows), symbol_bars.ticker)
        return len(rows)

    def _compute_rows(
        self,
        symbol_bars: SymbolBars,
        indicators: Sequence[Indicator],
        options: ComputeOptions,
        run_id: int | None,
    ) -> list[dict[str, Any]]:
        bars = symbol_bars.bars
        rows: list[dict[str, Any]] = []
        for indicator in indicators:
            points = indicator.compute(bars)
            for point in points:
                if not _in_window(point.bar_date, options.from_date, options.to_date):
                    continue
                rows.append(
                    self._point_to_row(symbol_bars, indicator, point, options, run_id)
                )
        return rows

    @staticmethod
    def _point_to_row(
        symbol_bars: SymbolBars,
        indicator: Indicator,
        point: IndicatorPoint,
        options: ComputeOptions,
        run_id: int | None,
    ) -> dict[str, Any]:
        values_json = json.dumps(point.values) if point.values is not None else None
        return {
            "symbol_id": symbol_bars.symbol_id,
            "ticker": symbol_bars.ticker,
            "bar_date": point.bar_date,
            "indicator_code": indicator.code,
            "indicator_version": indicator.version,
            "adjustment_type": options.adjustment_type,
            "value": point.value,
            "values_json": values_json,
            "indicator_run_id": run_id,
        }

    # ── run tracking ─────────────────────────────────────────────────────────

    def _create_run(self, options: ComputeOptions, symbols_count: int) -> int:
        assert self._engine is not None
        with self._engine.begin() as conn:
            return conn.execute(
                text("""
                    INSERT INTO indicators.indicator_runs (
                        mode, adjustment_type, requested_start_date, requested_end_date,
                        symbols_requested, heartbeat_at
                    ) VALUES (
                        :mode, :adjustment_type, :start_date, :end_date, :symbols_count, now()
                    ) RETURNING id
                """),
                {
                    "mode": options.mode,
                    "adjustment_type": options.adjustment_type,
                    "start_date": options.from_date,
                    "end_date": options.to_date,
                    "symbols_count": symbols_count,
                },
            ).scalar_one()

    def _heartbeat(self, run_id: int | None) -> None:
        if run_id is None or self._engine is None:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE indicators.indicator_runs SET heartbeat_at = now() WHERE id = :run_id"),
                {"run_id": run_id},
            )

    def _finalize_run(self, run_id: int, summary: ComputeSummary) -> None:
        assert self._engine is not None
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE indicators.indicator_runs
                    SET status = :status,
                        symbols_succeeded = :succeeded,
                        symbols_failed = :failed,
                        indicators_run = :indicators_run,
                        values_upserted = :values,
                        errors = :errors,
                        error_message = :error_message,
                        duration_seconds = :duration,
                        finished_at = now()
                    WHERE id = :run_id
                """),
                {
                    "status": "completed" if summary.status == "ok" else summary.status,
                    "succeeded": summary.symbols_succeeded,
                    "failed": summary.symbols_failed,
                    "indicators_run": summary.indicators_run,
                    "values": summary.values_upserted,
                    "errors": summary.errors,
                    "error_message": "; ".join(summary.failures[:5]) if summary.failures else None,
                    "duration": summary.duration_seconds,
                    "run_id": run_id,
                },
            )

    def latest_run_summary(self) -> dict[str, Any] | None:
        assert self._engine is not None
        with self._engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, mode, status, adjustment_type,
                           requested_start_date, requested_end_date,
                           symbols_requested, symbols_succeeded, symbols_failed,
                           indicators_run, values_upserted, errors,
                           duration_seconds, started_at, finished_at
                    FROM indicators.indicator_runs
                    ORDER BY id DESC
                    LIMIT 1
                """)
            ).mappings().first()
        return dict(row) if row is not None else None

    # ── fixture mode ─────────────────────────────────────────────────────────

    def _run_fixture(self, options: ComputeOptions, summary: ComputeSummary, started: float) -> ComputeSummary:
        """Compute indicators from a local bars fixture (JSON), no DB required."""
        from pathlib import Path

        fixture_path = Path(options.fixture_path)  # type: ignore[arg-type]
        files = sorted(fixture_path.glob("*.json")) if fixture_path.is_dir() else [fixture_path]
        indicators = self._resolve_indicators(options)
        summary.indicators_run = len(indicators)

        for fpath in files:
            log.info("loading bars fixture %s", fpath)
            with open(fpath) as f:
                data = json.load(f)
            ticker = data.get("ticker", fpath.stem)
            symbol_id = int(data.get("symbol_id", 0))
            bars = [Bar.from_payload(item) for item in data.get("bars", [])]
            symbol_bars = SymbolBars(symbol_id=symbol_id, ticker=ticker, bars=bars)
            summary.symbols_requested += 1

            try:
                rows = self._compute_rows(symbol_bars, indicators, options, run_id=None)
            except Exception as exc:  # noqa: BLE001
                summary.symbols_failed += 1
                summary.errors += 1
                summary.failures.append(f"{ticker}: {exc}")
                continue

            if options.dry_run or self._engine is None:
                summary.values_upserted += len(rows)
                summary.symbols_succeeded += 1
                for row in rows[:10]:
                    printable = row["value"] if row["value"] is not None else row["values_json"]
                    print(f"  {ticker}  {row['bar_date']}  {row['indicator_code']}={printable}")
            else:
                with self._engine.begin() as conn:
                    if rows:
                        conn.execute(UPSERT_INDICATOR_VALUE, rows)
                summary.values_upserted += len(rows)
                summary.symbols_succeeded += 1

        summary.status = "ok" if summary.errors == 0 else "failed"
        summary.duration_seconds = time.monotonic() - started
        return summary


def _in_window(value: date, from_date: date | None, to_date: date | None) -> bool:
    if from_date is not None and value < from_date:
        return False
    if to_date is not None and value > to_date:
        return False
    return True

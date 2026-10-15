"""Tests for the indicator compute job (fixture / dry-run, no database)."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quant_indicators.bars.models import Bar, SymbolBars
from quant_indicators.compute.job import ComputeOptions, IndicatorComputeJob
from quant_indicators.indicators.registry import all_indicators

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bars"


def test_compute_fixture_dry_run_produces_values():
    job = IndicatorComputeJob(engine=None)
    options = ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True)
    summary = job.run(options)

    assert summary.symbols_requested >= 1
    assert summary.symbols_succeeded == summary.symbols_requested
    assert summary.symbols_failed == 0
    assert summary.values_upserted > 0
    assert summary.status == "ok"


def test_compute_fixture_respects_indicator_selection():
    job = IndicatorComputeJob(engine=None)
    options = ComputeOptions(
        fixture_path=str(FIXTURE_DIR),
        dry_run=True,
        indicator_codes=["sma_50"],
    )
    summary = job.run(options)
    assert summary.indicators_run == 1
    assert summary.values_upserted > 0


@pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
def test_compute_upsert_success_is_debug_only(caplog, level):
    payload = json.loads((FIXTURE_DIR / "AAPL.json").read_text())
    symbol_bars = SymbolBars(
        symbol_id=1,
        ticker="AAPL",
        bars=[Bar.from_payload(item) for item in payload["bars"]],
    )
    engine = MagicMock()
    job = IndicatorComputeJob(engine=engine)
    indicators = [indicator for indicator in all_indicators() if indicator.code == "sma_50"]

    with caplog.at_level(level, logger="quant_indicators.compute.job"):
        upserted = job._compute_and_store(symbol_bars, indicators, ComputeOptions(), run_id=1)

    assert upserted == 1
    execute = engine.begin.return_value.__enter__.return_value.execute
    execute.assert_called_once()
    assert len(execute.call_args.args[1]) == upserted
    records = [
        record for record in caplog.records
        if record.name == "quant_indicators.compute.job"
    ]
    if level == logging.DEBUG:
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        assert records[0].getMessage() == "upserted 1 indicator values for AAPL"
    else:
        assert records == []


def test_compute_fixture_stores_latest_point_per_output():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))

    # Append-only model with flattened multi-output indicators: one row per
    # indicator output component, using only the most recent computed point.
    payload = json.loads((FIXTURE_DIR / "AAPL.json").read_text())
    bars = [Bar.from_payload(item) for item in payload["bars"]]

    max_abs = 10**12 - 1

    def storable(value: float | None) -> bool:
        return value is None or (math.isfinite(value) and abs(value) <= max_abs)

    expected_rows_per_symbol = 0
    for indicator in all_indicators():
        points = indicator.compute(bars)
        if not points:
            continue
        point = points[-1]
        if point.values is not None:
            expected_rows_per_symbol += sum(1 for v in point.values.values() if storable(v))
        elif storable(point.value):
            expected_rows_per_symbol += 1

    assert summary.symbols_requested >= 1
    assert summary.values_upserted == expected_rows_per_symbol * summary.symbols_requested


def test_compute_fixture_backfill_stores_full_series():
    job = IndicatorComputeJob(engine=None)
    appended = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))
    backfilled = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True, backfill=True))

    payload = json.loads((FIXTURE_DIR / "AAPL.json").read_text())
    bars = [Bar.from_payload(item) for item in payload["bars"]]

    max_abs = 10**12 - 1

    def storable(value: float | None) -> bool:
        return value is None or (math.isfinite(value) and abs(value) <= max_abs)

    expected_full = 0
    for indicator in all_indicators():
        for point in indicator.compute(bars):
            if point.values is not None:
                expected_full += sum(1 for v in point.values.values() if storable(v))
            elif storable(point.value):
                expected_full += 1

    # Backfill stores the entire computed series; append-only stores only the
    # latest day, so backfill must produce strictly more rows.
    assert backfilled.values_upserted == expected_full * backfilled.symbols_requested
    assert backfilled.values_upserted > appended.values_upserted


def test_compute_reuses_and_closes_bars_session(monkeypatch):
    from quant_indicators.bars.models import SymbolBars
    from quant_indicators.compute import job as job_module

    class FakeSession:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

    session = FakeSession()
    seen_sessions = []
    job = IndicatorComputeJob(engine=object(), indicators=[])
    monkeypatch.setattr(job_module.requests, "Session", lambda: session)
    monkeypatch.setattr(job, "sync_definitions", lambda _indicators: 0)
    monkeypatch.setattr(job, "_create_run", lambda _options, _count: 1)
    monkeypatch.setattr(job, "_heartbeat", lambda _run_id: None)
    monkeypatch.setattr(job, "_prune_old_values", lambda _cutoff: 0)
    monkeypatch.setattr(job, "_finalize_run", lambda _run_id, _summary: None)

    def list_symbols(**kwargs):
        seen_sessions.append(kwargs["session"])
        return [(1, "ONE"), (2, "TWO")]

    def load_symbol(**kwargs):
        seen_sessions.append(kwargs["session"])
        return SymbolBars(symbol_id=kwargs["symbol_id"], ticker=kwargs["ticker"], bars=[])

    monkeypatch.setattr(job_module, "list_symbols_with_bars", list_symbols)
    monkeypatch.setattr(job_module, "load_symbol_bars", load_symbol)

    summary = job.run(ComputeOptions())

    assert len(seen_sessions) == 3
    assert all(seen_session is session for seen_session in seen_sessions)
    assert session.closed
    assert summary.symbols_skipped == 2


def test_summary_format_line():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))
    line = summary.format_line()
    assert "compute_summary" in line
    assert "values_upserted=" in line

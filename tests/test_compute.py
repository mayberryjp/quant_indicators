"""Tests for the indicator compute job (fixture / dry-run, no database)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from quant_indicators.bars.models import Bar
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


def test_compute_fixture_stores_daily_history_per_output():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))

    # Daily-history model with flattened multi-output indicators: one row per
    # (indicator output component, bar_date) that produced a storable value.
    payload = json.loads((FIXTURE_DIR / "AAPL.json").read_text())
    bars = [Bar.from_payload(item) for item in payload["bars"]]

    max_abs = 10**12 - 1

    def storable(value: float | None) -> bool:
        return value is None or (math.isfinite(value) and abs(value) <= max_abs)

    expected_rows_per_symbol = 0
    for indicator in all_indicators():
        for point in indicator.compute(bars):
            if point.values is not None:
                expected_rows_per_symbol += sum(1 for v in point.values.values() if storable(v))
            elif storable(point.value):
                expected_rows_per_symbol += 1

    assert summary.symbols_requested >= 1
    assert summary.values_upserted == expected_rows_per_symbol * summary.symbols_requested
    # A daily history stores many rows per indicator, not a single current value.
    assert summary.values_upserted > len(all_indicators())


def test_summary_format_line():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))
    line = summary.format_line()
    assert "compute_summary" in line
    assert "values_upserted=" in line

"""Tests for the indicator compute job (fixture / dry-run, no database)."""

from __future__ import annotations

from pathlib import Path

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


def test_compute_fixture_stores_one_value_per_indicator_output():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))

    # Current-value model with flattened multi-output indicators: one row per
    # (symbol, indicator output component) that produced output.
    expected_rows_per_symbol = sum(
        len(ind.outputs) if ind.outputs else 1
        for ind in all_indicators()
    )
    assert summary.symbols_requested >= 1
    assert summary.values_upserted == expected_rows_per_symbol * summary.symbols_requested


def test_summary_format_line():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))
    line = summary.format_line()
    assert "compute_summary" in line
    assert "values_upserted=" in line

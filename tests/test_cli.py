"""Tests for the CLI parser and fixture-backed commands (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_indicators._cli_impl import (
    EXPECTED_SCHEMA_VERSION,
    EXPECTED_TABLES,
    build_parser,
    main,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bars"


def test_expected_constants():
    assert EXPECTED_SCHEMA_VERSION == "0003_flatten_output_rows"
    assert set(EXPECTED_TABLES) == {
        "indicator_definitions",
        "indicator_runs",
        "indicator_values",
    }


def test_parser_requires_command():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_compute_defaults():
    parser = build_parser()
    args = parser.parse_args(["indicators", "compute", "--fixture", "x", "--dry-run"])
    assert args.fixture == "x"
    assert args.dry_run is True


def test_indicators_list_runs(capsys):
    assert main(["indicators", "list"]) == 0
    out = capsys.readouterr().out
    assert "registered_indicators=" in out
    assert "sma_50" in out


def test_indicators_compute_fixture_dry_run(capsys):
    rc = main(["indicators", "compute", "--fixture", str(FIXTURE_DIR), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "compute_summary" in out

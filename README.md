# quant_indicators

Daily technical-indicator pipeline for Alpaca bars. It reads OHLCV daily bars
produced by [`quant_daily_bars`](https://github.com/mayberryjp/quant_daily_bars)
from Postgres, computes a pluggable set of technical indicators for every
ticker, stores them idempotently, and exposes a read-only HTTP API to retrieve
them.

## Architecture

```
market_data.daily_bars ──▶ compute job ──▶ indicators.indicator_values ──▶ retrieval API
   (owned by                (registry of                (this service's           (Bottle + waitress)
    quant_daily_bars)        indicators)                 own schema)
```

The service runs in a single container orchestrated by `supervisord`:

| Program                 | Responsibility                                            |
| ----------------------- | --------------------------------------------------------- |
| `db-migrate`            | `alembic upgrade head` on startup (one-shot).             |
| `indicators-compute`    | Recompute indicators once per day at `COMPUTE_SCHEDULE_TIME`. |
| `quant-indicators-api`  | Serve the retrieval API (`API_PORT`, default 8001).       |

## Schema

All state lives in a dedicated `indicators` Postgres schema with its own Alembic
version table (`indicators.alembic_version_indicators`), so it never collides
with the `market_data` schema owned by `quant_daily_bars`.

- `indicator_definitions` — registry metadata (code, version, outputs, params).
- `indicator_runs` — one row per compute run, with heartbeat and counts.
- `indicator_values` — the **current** value of each indicator, unique per
  `(symbol_id, indicator_code, indicator_version, adjustment_type)`. `bar_date`
  is kept as an as-of column (the bar the value was computed from), not part of
  the key — each run overwrites the row, so no history accumulates.

Single-output indicators (e.g. SMA) write one row under their base code
(`sma_50`). Multi-output indicators (e.g. MACD) also write to `value`, but as
multiple suffixed rows (`macd_macd`, `macd_signal`, `macd_histogram`).

## Indicators

Indicators are pluggable: subclass `Indicator`, decorate with `@register`, and
the compute job and CLI pick them up automatically — no pipeline changes. Run
`quant-indicators indicators list` for the full registered set (57 and counting).

**Moving averages** (`averages.py`, `core.py`)

| Code | Description |
| ---- | ----------- |
| `sma_10` / `sma_20` / `sma_50` / `sma_100` / `sma_200` | Simple moving averages |
| `ema_9` / `ema_12` / `ema_26` / `ema_50` / `ema_200` | Exponential moving averages (SMA-seeded) |
| `wma_20` | Linearly weighted moving average |
| `hma_20` | Hull moving average |
| `dema_20` / `tema_20` | Double / triple exponential moving averages |
| `vwma_20` | Volume-weighted moving average |

**Momentum / oscillators** (`core.py`, `momentum.py`)

| Code | Description |
| ---- | ----------- |
| `rsi_14` | Relative Strength Index (Wilder) |
| `macd` | MACD line / signal / histogram |
| `ppo` | Percentage Price Oscillator (ppo/signal/histogram) |
| `stoch_14_3` | Stochastic Oscillator (%K / %D) |
| `stochrsi_14` | Stochastic RSI (stochrsi / %K / %D) |
| `willr_14` | Williams %R |
| `cci_20` | Commodity Channel Index |
| `roc_12` / `mom_10` | Rate of change / momentum |
| `mfi_14` | Money Flow Index |
| `cmo_14` | Chande Momentum Oscillator |
| `tsi` | True Strength Index |
| `ao` | Awesome Oscillator |
| `uo` | Ultimate Oscillator |

**Volatility / channels** (`core.py`, `volatility.py`)

| Code | Description |
| ---- | ----------- |
| `atr_14` | Average True Range |
| `bbands_20_2` | Bollinger Bands (middle/upper/lower/bandwidth) |
| `keltner_20` | Keltner Channels (middle/upper/lower) |
| `donchian_20` | Donchian Channels (upper/lower/middle) |
| `hv_20` | Annualized historical volatility |
| `ulcer_14` | Ulcer Index |
| `stddev_20` | Rolling standard deviation of close |

**Volume** (`core.py`, `volume.py`)

| Code | Description |
| ---- | ----------- |
| `obv` | On-Balance Volume |
| `adl` | Accumulation/Distribution Line |
| `cmf_20` | Chaikin Money Flow |
| `chaikin_osc` | Chaikin Oscillator |
| `force_index_13` | Force Index |
| `eom_14` | Ease of Movement |
| `pvt` | Price Volume Trend |
| `vol_sma_20` | Volume simple moving average |

**Trend** (`trend.py`)

| Code | Description |
| ---- | ----------- |
| `adx_14` | ADX with +DI / -DI |
| `aroon_25` | Aroon Up/Down and oscillator |
| `vortex_14` | Vortex Indicator (+VI / -VI) |
| `trix_15` | TRIX |
| `dpo_20` | Detrended Price Oscillator |
| `psar` | Parabolic SAR (sar / trend) |

**Levels** (`levels.py`)

| Code | Description |
| ---- | ----------- |
| `support_resistance_20` / `_50` / `_100` / `_252` | Rolling low/high levels |
| `volume_shelf_60` | Volume-by-price POC and 70% value area |
| `pivot_points` | Classic floor-trader pivots (P/R1-3/S1-3) |
| `pivot_fib` | Fibonacci pivots (P/R1-3/S1-3) |

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, runs migrations, computes indicators, and serves the API
on `http://localhost:8001`.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate        # or: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Tests run without a database or network — indicator math, the registry, the
compute job (fixture / dry-run mode), the CLI, and the API (injected fake
engine) are all covered.

## CLI

```bash
python -m quant_indicators.cli db upgrade
python -m quant_indicators.cli db verify
python -m quant_indicators.cli indicators list
python -m quant_indicators.cli indicators sync-definitions

# One-shot compute of current values for specific tickers
python -m quant_indicators.cli indicators compute --tickers AAPL,MSFT

# Continuous daily recompute (used by supervisord)
python -m quant_indicators.cli indicators compute --schedule 86400

# Compute from a bars fixture without touching the database
python -m quant_indicators.cli indicators compute --fixture tests/fixtures/bars --dry-run

python -m quant_indicators.cli indicators run-summary --latest
```

Each run computes and overwrites the current value of every indicator per
ticker; there is no date window. `--lookback-days` (default `400`) sets how much
recent history is loaded per symbol so long-window indicators such as `sma_200`
and `support_resistance_252` warm up correctly. A late-arriving bar is picked up
automatically on the next run.

## Retrieval API

| Method / Route                          | Description                              |
| --------------------------------------- | ---------------------------------------- |
| `GET /health`                           | Liveness probe.                          |
| `GET /ready`                            | Readiness: DB migrated to expected schema. |
| `GET /indicators`                       | List registered/active indicator definitions. |
| `GET /indicators/values`                | Query values (`ticker`, `indicator`, `adjustment_type`, `limit`, `offset`). |
| `GET /indicators/values/latest/<ticker>`| Current value of each indicator for a ticker. |
| `GET /indicators/coverage`              | Per-ticker/indicator as-of date. |
| `GET /runs`                             | Recent compute runs.                     |
| `GET /runs/latest`                      | Most recent run.                         |
| `GET /runs/<id>`                        | A specific run.                          |

## Configuration

See `.env.example`. Key variables:

| Variable                    | Default                          | Purpose                             |
| --------------------------- | -------------------------------- | ----------------------------------- |
| `DATABASE_URL`              | `postgresql+psycopg://quant:...` | Postgres connection.                |
| `BARS_SCHEMA` / `BARS_TABLE`| `market_data` / `daily_bars`     | Where input bars are read from.     |
| `INDICATOR_ADJUSTMENT_TYPE` | `unadjusted`                     | Default price series.               |
| `INDICATOR_LOOKBACK_DAYS`   | `400`                            | Recent history loaded per symbol for warm-up. |
| `COMPUTE_SCHEDULE_TIME`     | `01:00`                          | Wall-clock `HH:MM` for the daily compute run. |
| `COMPUTE_SCHEDULE_TIMEZONE` | `UTC`                            | IANA timezone for `COMPUTE_SCHEDULE_TIME`. |
| `API_LISTEN_ADDRESS` / `API_PORT` | `0.0.0.0` / `8001`         | API bind address.                   |

from __future__ import annotations

from datetime import date, timedelta

from quant_indicators.bars.source import list_symbols_with_bars, load_symbol_bars


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[dict]):
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict, int]] = []

    def get(self, url: str, *, params: dict, timeout: int) -> FakeResponse:
        self.calls.append((url, params, timeout))
        return FakeResponse(next(self.responses))


def test_coverage_and_bar_pages_use_the_same_session():
    def item(bar_date: date) -> dict:
        return {
            "bar_date": bar_date.isoformat(),
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
            "volume": 10,
        }

    oldest_date = date(2020, 1, 1)
    newest_first_page = [item(oldest_date + timedelta(days=i)) for i in range(500, 0, -1)]
    session = FakeSession([
        {"items": [{"symbol_id": 7, "ticker": "TEST"}]},
        {"items": newest_first_page},
        {"items": [item(oldest_date)]},
    ])

    symbols = list_symbols_with_bars(adjustment_type="unadjusted", session=session)
    bars = load_symbol_bars(
        symbol_id=7,
        ticker="TEST",
        adjustment_type="unadjusted",
        start_date=None,
        end_date=None,
        session=session,
    )

    assert symbols == [(7, "TEST")]
    assert len(bars.bars) == 501
    assert bars.bars[0].bar_date == oldest_date
    assert [call[1]["offset"] for call in session.calls[1:]] == [0, 500]
    assert all(call[0].endswith("/bars") for call in session.calls[1:])
"""Tests for bar ingestion helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from bars.ingestion import (
    _clean_rows,
    fetch_daily_bars,
    ingest_symbol,
    upsert_bars,
)
from bars.models import Bar, Symbol


def _utc(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_clean_rows_drops_nan_and_dedupes():
    ts1 = _utc(2024, 1, 2)
    ts2 = _utc(2024, 1, 3)

    rows = [
        {"ts": ts1, "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1_000_000},
        {"ts": ts2, "open": float("nan"), "high": 101, "low": 99, "close": 100, "volume": 1},
        {"ts": ts1, "open": 200, "high": 201, "low": 199, "close": 200.5, "volume": 2_000_000},
    ]

    cleaned = _clean_rows(rows)

    assert len(cleaned) == 1
    only = cleaned[0]
    assert only["ts"] == ts1
    assert only["open"] == Decimal("200")
    assert only["close"] == Decimal("200.5")


def test_clean_rows_localizes_naive_timestamps_to_utc():
    naive = datetime(2024, 1, 2)
    cleaned = _clean_rows(
        [{"ts": naive, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
    )
    assert cleaned[0]["ts"] == _utc(2024, 1, 2)


@pytest.mark.django_db
def test_upsert_bars_inserts_then_updates():
    symbol = Symbol.objects.create(ticker="TEST")

    rows = [
        {"ts": _utc(2024, 1, 2), "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},
        {"ts": _utc(2024, 1, 3), "open": 2, "high": 3, "low": 2, "close": 2.5, "volume": 20},
    ]
    inserted = upsert_bars(symbol, rows)
    assert inserted == 2
    assert Bar.objects.filter(symbol=symbol).count() == 2

    rows[0]["close"] = 9.99
    updated = upsert_bars(symbol, rows)
    assert updated == 2
    assert Bar.objects.filter(symbol=symbol).count() == 2
    bar = Bar.objects.get(symbol=symbol, ts=_utc(2024, 1, 2))
    assert bar.close == Decimal("9.99")


def _fake_yf_dataframe(start: datetime, n: int) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n)],
            "High": [101.0 + i for i in range(n)],
            "Low": [99.0 + i for i in range(n)],
            "Close": [100.5 + i for i in range(n)],
            "Volume": [1_000_000 + i for i in range(n)],
        },
        index=idx,
    )


def test_fetch_daily_bars_normalizes_dataframe(monkeypatch):
    n = 4
    df = _fake_yf_dataframe(start=datetime(2024, 1, 2, tzinfo=timezone.utc), n=n)

    class FakeTicker:
        def __init__(self, *a, **k):
            pass

        def history(self, **kwargs):
            return df

    monkeypatch.setattr("bars.ingestion.yf.Ticker", FakeTicker)

    rows = fetch_daily_bars(
        "TEST",
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 6, tzinfo=timezone.utc),
    )
    assert len(rows) == n
    first = rows[0]
    assert first["ts"] == _utc(2024, 1, 2)
    assert first["open"] == 100.0
    assert first["volume"] == 1_000_000


@pytest.mark.django_db
def test_ingest_symbol_uses_fetch_and_upsert(monkeypatch):
    symbol = Symbol.objects.create(ticker="DEMO")

    fake_rows = [
        {
            "ts": _utc(2024, 1, 2),
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        },
        {
            "ts": _utc(2024, 1, 3),
            "open": 2,
            "high": 3,
            "low": 1.5,
            "close": 2.5,
            "volume": 20,
        },
    ]
    with patch("bars.ingestion.fetch_daily_bars", return_value=fake_rows) as fetch:
        result = ingest_symbol(
            symbol,
            start=_utc(2024, 1, 1),
            end=_utc(2024, 1, 4),
        )

    fetch.assert_called_once()
    assert result.symbol == "DEMO"
    assert result.fetched == 2
    assert result.upserted == 2
    assert Bar.objects.filter(symbol=symbol).count() == 2

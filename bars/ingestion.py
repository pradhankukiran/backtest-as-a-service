"""Bar ingestion: fetch from yfinance and upsert into the Bar hypertable."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import yfinance as yf
from django.db import transaction
from django.utils import timezone as djtz

from .models import Bar, Symbol

log = logging.getLogger(__name__)

NUMERIC_FIELDS = ("open", "high", "low", "close", "volume")
UPDATE_FIELDS = ["open", "high", "low", "close", "volume", "updated_at"]


@dataclass(frozen=True)
class IngestResult:
    symbol: str
    timeframe: str
    fetched: int
    upserted: int
    skipped: int
    earliest: datetime | None
    latest: datetime | None


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return Decimal(str(value))


def fetch_daily_bars(
    ticker: str,
    start: datetime,
    end: datetime,
    *,
    interval: str = "1d",
    max_attempts: int = 4,
) -> list[dict]:
    """Fetch OHLCV bars for `ticker` between [start, end). Returns a list of
    dicts {ts, open, high, low, close, volume} ready for upsert.

    Uses split/dividend-adjusted closes (auto_adjust=True), which is what
    backtests almost always want. Bars are normalized to UTC.
    """
    delay = 2.0
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            df = yf.Ticker(ticker).history(
                start=start.date().isoformat(),
                end=end.date().isoformat(),
                interval=interval,
                auto_adjust=True,
                actions=False,
                raise_errors=True,
                timeout=15,
            )
            break
        except Exception as exc:  # yfinance raises a variety of subtypes
            last_exc = exc
            log.warning(
                "yfinance fetch failed (ticker=%s attempt=%d): %s",
                ticker,
                attempt,
                exc,
            )
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    else:
        raise RuntimeError(f"yfinance fetch exhausted retries for {ticker}") from last_exc

    if df is None or df.empty:
        return []

    df = df.rename(columns=str.lower).reset_index()
    ts_col = next(c for c in df.columns if c.lower() in {"date", "datetime"})

    rows: list[dict] = []
    for record in df.itertuples(index=False):
        ts = getattr(record, ts_col)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts_utc = ts.tz_convert("UTC").to_pydatetime()
        row = {
            "ts": ts_utc,
            "open": getattr(record, "open"),
            "high": getattr(record, "high"),
            "low": getattr(record, "low"),
            "close": getattr(record, "close"),
            "volume": getattr(record, "volume", 0) or 0,
        }
        rows.append(row)
    return rows


def _clean_rows(rows: list[dict]) -> list[dict]:
    """Drop NaN/Inf bars, force tz-aware UTC timestamps, dedupe by ts (last wins)."""
    by_ts: dict[datetime, dict] = {}
    for row in rows:
        decs = {field: _to_decimal(row.get(field)) for field in NUMERIC_FIELDS}
        if any(value is None for value in decs.values()):
            continue

        ts = row["ts"]
        if djtz.is_naive(ts):
            ts = djtz.make_aware(ts, timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        by_ts[ts] = {**decs, "ts": ts}
    return list(by_ts.values())


@transaction.atomic
def upsert_bars(symbol: Symbol, rows: list[dict], timeframe: str = "1d") -> int:
    """Bulk-upsert OHLCV rows for `symbol` at `timeframe`. Returns the number of
    rows touched (inserted or updated)."""
    cleaned = _clean_rows(rows)
    if not cleaned:
        return 0
    objs = [Bar(symbol=symbol, timeframe=timeframe, **row) for row in cleaned]
    Bar.objects.bulk_create(
        objs,
        update_conflicts=True,
        unique_fields=["symbol", "ts", "timeframe"],
        update_fields=UPDATE_FIELDS,
        batch_size=1000,
    )
    return len(objs)


def ingest_symbol(
    symbol: Symbol,
    *,
    days_back: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    timeframe: str = "1d",
) -> IngestResult:
    """Fetch + upsert daily bars for one symbol. Range can be specified by
    explicit (start, end) or relative `days_back` from now (default 30d)."""
    end = end or djtz.now()
    if start is None:
        start = end - timedelta(days=days_back if days_back is not None else 30)

    rows = fetch_daily_bars(symbol.ticker, start, end, interval=timeframe)
    upserted = upsert_bars(symbol, rows, timeframe=timeframe)
    skipped = len(rows) - upserted

    return IngestResult(
        symbol=symbol.ticker,
        timeframe=timeframe,
        fetched=len(rows),
        upserted=upserted,
        skipped=skipped,
        earliest=rows[0]["ts"] if rows else None,
        latest=rows[-1]["ts"] if rows else None,
    )

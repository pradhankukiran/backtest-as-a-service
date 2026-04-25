"""Celery tasks for bar ingestion."""

from __future__ import annotations

import logging
from dataclasses import asdict

from celery import shared_task

from .ingestion import ingest_symbol
from .models import Symbol

log = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="bars.ingest_bars",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def ingest_bars(
    self,
    ticker: str,
    *,
    days_back: int | None = None,
    timeframe: str = "1d",
) -> dict:
    """Fetch + upsert bars for a single ticker. Defaults to the last 30 days."""
    try:
        symbol = Symbol.objects.get(ticker=ticker)
    except Symbol.DoesNotExist:
        log.warning("ingest_bars: unknown symbol %s", ticker)
        return {"symbol": ticker, "error": "unknown_symbol"}

    result = ingest_symbol(symbol, days_back=days_back, timeframe=timeframe)
    log.info(
        "ingest_bars %s tf=%s fetched=%d upserted=%d",
        result.symbol,
        result.timeframe,
        result.fetched,
        result.upserted,
    )
    payload = asdict(result)
    payload["earliest"] = result.earliest.isoformat() if result.earliest else None
    payload["latest"] = result.latest.isoformat() if result.latest else None
    return payload


@shared_task(name="bars.ingest_all_active_bars")
def ingest_all_active_bars(days_back: int = 5, timeframe: str = "1d") -> int:
    """Enqueue an ingest_bars task for every active Symbol. Returns the count
    enqueued. Designed to be driven by Celery beat on a daily schedule."""
    tickers = list(Symbol.objects.filter(is_active=True).values_list("ticker", flat=True))
    for ticker in tickers:
        ingest_bars.delay(ticker, days_back=days_back, timeframe=timeframe)
    return len(tickers)

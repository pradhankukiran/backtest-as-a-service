"""Celery tasks for backtest execution."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone

from celery import shared_task
from django.utils import timezone as djtz

from .engine import load_bars_dataframe, run_backtest_engine
from .models import BacktestRun
from .persistence import save_run_results

log = logging.getLogger(__name__)


@shared_task(bind=True, name="runs.run_backtest")
def run_backtest(self, run_id: int) -> dict:
    """Execute one BacktestRun end-to-end. Updates the run row in place.

    Single-symbol for Phase 3: takes the first symbol from `run.symbols`.
    Multi-symbol fan-out is a Phase 5 feature.
    """
    try:
        run = BacktestRun.objects.select_related("strategy").get(id=run_id)
    except BacktestRun.DoesNotExist:
        log.warning("run_backtest: unknown run_id=%s", run_id)
        return {"run_id": run_id, "error": "unknown_run"}

    started_at = djtz.now()
    BacktestRun.objects.filter(id=run.id).update(
        status=BacktestRun.Status.RUNNING,
        started_at=started_at,
        finished_at=None,
        duration_ms=None,
        error="",
    )

    try:
        symbol = run.symbols.first()
        if symbol is None:
            raise ValueError("Run has no symbols configured")

        start_dt = datetime.combine(run.start_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(run.end_date, time.max, tzinfo=timezone.utc)

        df = load_bars_dataframe(symbol, start_dt, end_dt, timeframe=run.timeframe)
        if df.empty:
            raise ValueError(
                f"No bars for {symbol.ticker} {run.timeframe} "
                f"in {run.start_date}..{run.end_date}"
            )

        result = run_backtest_engine(
            code=run.strategy.code,
            entrypoint=run.strategy.entrypoint,
            df=df,
            cash=float(run.initial_capital),
            commission_bps=run.commission_bps,
            params=run.params or {},
        )
        save_run_results(run, result)
        final_status = BacktestRun.Status.SUCCEEDED
        error_msg = ""
    except Exception as exc:
        log.exception("run_backtest failed run_id=%s", run_id)
        final_status = BacktestRun.Status.FAILED
        error_msg = f"{type(exc).__name__}: {exc}"[:5000]

    finished_at = djtz.now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    BacktestRun.objects.filter(id=run.id).update(
        status=final_status,
        finished_at=finished_at,
        duration_ms=duration_ms,
        error=error_msg,
    )

    return {
        "run_id": run.id,
        "status": final_status,
        "duration_ms": duration_ms,
        "error": error_msg,
    }

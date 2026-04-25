"""Celery tasks for backtest execution and parameter sweeps."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

from celery import chord, shared_task
from django.db import transaction
from django.utils import timezone as djtz

from .engine import load_bars_dataframe, run_backtest_engine
from .models import BacktestRun, ParameterSweep
from .persistence import save_run_results
from .sweeps import grid_size, iter_combos, merge_params

log = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="runs.run_backtest",
    queue="untrusted",
    time_limit=600,
    soft_time_limit=540,
)
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


@shared_task(name="runs.optimize")
def optimize(sweep_id: int) -> dict:
    """Materialize child BacktestRuns for every grid combo and dispatch them as
    a Celery chord. The `finalize_sweep` callback aggregates child results.
    """
    try:
        sweep = ParameterSweep.objects.select_related("strategy").get(id=sweep_id)
    except ParameterSweep.DoesNotExist:
        log.warning("optimize: unknown sweep_id=%s", sweep_id)
        return {"sweep_id": sweep_id, "error": "unknown_sweep"}

    expected = grid_size(sweep.grid)

    with transaction.atomic():
        sweep.status = ParameterSweep.Status.RUNNING
        sweep.started_at = djtz.now()
        sweep.children_total = expected
        sweep.children_succeeded = 0
        sweep.children_failed = 0
        sweep.error = ""
        sweep.save(
            update_fields=[
                "status",
                "started_at",
                "children_total",
                "children_succeeded",
                "children_failed",
                "error",
                "updated_at",
            ]
        )

        symbols = list(sweep.symbols.all())
        children: list[BacktestRun] = []
        for combo in iter_combos(sweep.grid):
            child = BacktestRun.objects.create(
                strategy=sweep.strategy,
                sweep=sweep,
                created_by=sweep.created_by,
                timeframe=sweep.timeframe,
                start_date=sweep.start_date,
                end_date=sweep.end_date,
                initial_capital=sweep.initial_capital,
                commission_bps=sweep.commission_bps,
                slippage_bps=sweep.slippage_bps,
                params=merge_params(sweep.base_params, combo),
            )
            child.symbols.set(symbols)
            children.append(child)

    header = [run_backtest.s(child.id) for child in children]
    callback = finalize_sweep.s(sweep.id)
    chord(header, callback).apply_async()

    return {"sweep_id": sweep.id, "children_queued": len(children)}


@shared_task(name="runs.finalize_sweep")
def finalize_sweep(child_results: list, sweep_id: int) -> dict:
    """Chord callback: tally child outcomes and finalize the parent sweep row."""
    succeeded = 0
    failed = 0
    for result in child_results or []:
        if isinstance(result, dict) and result.get("status") == BacktestRun.Status.SUCCEEDED:
            succeeded += 1
        else:
            failed += 1

    finished_at = djtz.now()

    with transaction.atomic():
        sweep = ParameterSweep.objects.select_for_update().get(id=sweep_id)
        sweep.children_succeeded = succeeded
        sweep.children_failed = failed
        if succeeded == sweep.children_total:
            sweep.status = ParameterSweep.Status.SUCCEEDED
        elif succeeded > 0:
            sweep.status = ParameterSweep.Status.PARTIAL
        else:
            sweep.status = ParameterSweep.Status.FAILED
        sweep.finished_at = finished_at
        if sweep.started_at:
            sweep.duration_ms = int(
                (finished_at - sweep.started_at).total_seconds() * 1000
            )
        sweep.save(
            update_fields=[
                "status",
                "finished_at",
                "duration_ms",
                "children_succeeded",
                "children_failed",
                "updated_at",
            ]
        )

    return {
        "sweep_id": sweep_id,
        "status": sweep.status,
        "succeeded": succeeded,
        "failed": failed,
    }


@shared_task(name="runs.cleanup_stale_runs")
def cleanup_stale_runs(older_than_days: int = 90) -> dict:
    """Drop equity points and trades for old SUCCEEDED runs to keep the DB lean.

    The BacktestRun and RunMetrics rows are kept (they're small) so historical
    summaries still render; only the per-bar artefacts are pruned.
    """
    from .models import EquityPoint, Trade

    cutoff = djtz.now() - timedelta(days=older_than_days)
    stale_run_ids = list(
        BacktestRun.objects.filter(
            status=BacktestRun.Status.SUCCEEDED,
            finished_at__lt=cutoff,
        ).values_list("id", flat=True)
    )
    if not stale_run_ids:
        return {"runs_pruned": 0, "equity_points_deleted": 0, "trades_deleted": 0}

    eq_deleted, _ = EquityPoint.objects.filter(run_id__in=stale_run_ids).delete()
    tr_deleted, _ = Trade.objects.filter(run_id__in=stale_run_ids).delete()

    log.info(
        "cleanup_stale_runs pruned %d run(s); deleted %d equity point(s), %d trade(s)",
        len(stale_run_ids),
        eq_deleted,
        tr_deleted,
    )
    return {
        "runs_pruned": len(stale_run_ids),
        "equity_points_deleted": eq_deleted,
        "trades_deleted": tr_deleted,
    }

"""Server-rendered HTML views for runs (list + detail) and sweeps."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import BacktestRun, ParameterSweep, Trade
from .tasks import optimize, run_backtest


@require_GET
@login_required
def runs_list(request):
    runs = (
        BacktestRun.objects.select_related("strategy", "metrics")
        .prefetch_related("symbols")
        .order_by("-created_at")[:200]
    )
    return render(request, "runs/list.html", {"runs": runs})


@require_GET
@login_required
def run_detail(request, run_id: int):
    run = get_object_or_404(
        BacktestRun.objects.select_related("strategy", "metrics", "sweep").prefetch_related(
            "symbols"
        ),
        id=run_id,
    )
    trades = list(
        Trade.objects.filter(run=run).select_related("symbol").order_by("entry_ts")[:500]
    )
    return render(request, "runs/detail.html", {"run": run, "trades": trades})


@require_POST
@login_required
def rerun_run(request, run_id: int):
    run = get_object_or_404(BacktestRun, id=run_id)
    run_backtest.delay(run.id)
    messages.success(request, f"Re-queued run #{run.id}")
    return redirect("run-detail", run_id=run.id)


@require_GET
@login_required
def sweeps_list(request):
    sweeps = (
        ParameterSweep.objects.select_related("strategy")
        .prefetch_related("symbols")
        .order_by("-created_at")[:200]
    )
    return render(request, "runs/sweep_list.html", {"sweeps": sweeps})


@require_GET
@login_required
def sweep_detail(request, sweep_id: int):
    sweep = get_object_or_404(
        ParameterSweep.objects.select_related("strategy").prefetch_related("symbols"),
        id=sweep_id,
    )

    children = list(
        BacktestRun.objects.filter(sweep=sweep).select_related("metrics").order_by("id")
    )

    rows = []
    best_idx = None
    best_sharpe = None
    for idx, run in enumerate(children):
        metrics = getattr(run, "metrics", None)
        sharpe = metrics.sharpe_ratio if metrics else None
        if sharpe is not None and (best_sharpe is None or sharpe > best_sharpe):
            best_sharpe = sharpe
            best_idx = idx
        rows.append(
            {
                "run_id": run.id,
                "status": run.status,
                "params": run.params,
                "return_pct": metrics.return_pct if metrics else None,
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": metrics.max_drawdown_pct if metrics else None,
                "trade_count": metrics.trade_count if metrics else None,
                "final_equity": metrics.final_equity if metrics else None,
                "is_best": False,
            }
        )
    if best_idx is not None:
        rows[best_idx]["is_best"] = True

    return render(request, "runs/sweep_detail.html", {"sweep": sweep, "rows": rows})


@require_POST
@login_required
def rerun_sweep(request, sweep_id: int):
    sweep = get_object_or_404(ParameterSweep, id=sweep_id)
    optimize.delay(sweep.id)
    messages.success(request, f"Re-queued sweep #{sweep.id} ({sweep.children_total} child runs)")
    return redirect("sweep-detail", sweep_id=sweep.id)

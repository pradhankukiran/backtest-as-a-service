"""Server-rendered HTML views for runs (list + detail) and sweeps."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from bars.models import Bar, Symbol

from .models import BacktestRun, EquityPoint, ParameterSweep, Strategy, Trade
from .tasks import optimize, run_backtest


@require_GET
@login_required
def dashboard(request):
    """Data-driven landing: counts + latest run + top Sharpe + recent activity."""
    counts = {
        "runs": BacktestRun.objects.count(),
        "sweeps": ParameterSweep.objects.count(),
        "strategies": Strategy.objects.filter(is_active=True).count(),
        "symbols": Symbol.objects.filter(is_active=True).count(),
        "bars": Bar.objects.count(),
    }

    latest_run = (
        BacktestRun.objects.select_related("strategy", "metrics")
        .prefetch_related("symbols")
        .order_by("-created_at")
        .first()
    )

    sparkline_points: list[dict] = []
    if latest_run:
        sparkline_points = list(
            EquityPoint.objects.filter(run=latest_run)
            .order_by("ts")
            .values_list("equity", flat=True)
        )

    top_runs = list(
        BacktestRun.objects.filter(
            status=BacktestRun.Status.SUCCEEDED,
            metrics__sharpe_ratio__isnull=False,
        )
        .select_related("strategy", "metrics")
        .order_by("-metrics__sharpe_ratio")[:5]
    )

    latest_sweep = (
        ParameterSweep.objects.select_related("strategy")
        .prefetch_related("symbols")
        .order_by("-created_at")
        .first()
    )

    recent_runs = list(
        BacktestRun.objects.select_related("strategy", "metrics")
        .prefetch_related("symbols")
        .order_by("-created_at")[:6]
    )

    return render(
        request,
        "landing.html",
        {
            "counts": counts,
            "latest_run": latest_run,
            "sparkline": [float(v) for v in sparkline_points],
            "top_runs": top_runs,
            "latest_sweep": latest_sweep,
            "recent_runs": recent_runs,
        },
    )


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

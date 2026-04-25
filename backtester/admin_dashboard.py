"""Custom unfold admin dashboard callback.

Wired via UNFOLD["DASHBOARD_CALLBACK"] in settings.py and rendered through
templates/admin/index.html which overrides unfold's default index template
to inject these widgets above the standard app list.
"""

from __future__ import annotations


def dashboard_callback(request, context):
    from bars.models import Bar, Symbol
    from runs.models import BacktestRun, EquityPoint, ParameterSweep, Strategy

    context["bt_counts"] = {
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
    context["bt_latest_run"] = latest_run

    sparkline = []
    if latest_run:
        sparkline = [
            float(v)
            for v in EquityPoint.objects.filter(run=latest_run)
            .order_by("ts")
            .values_list("equity", flat=True)
        ]
    context["bt_sparkline"] = ",".join(f"{v:.4f}" for v in sparkline)

    context["bt_top_runs"] = list(
        BacktestRun.objects.filter(
            status=BacktestRun.Status.SUCCEEDED,
            metrics__sharpe_ratio__isnull=False,
        )
        .select_related("strategy", "metrics")
        .order_by("-metrics__sharpe_ratio")[:5]
    )

    context["bt_latest_sweep"] = (
        ParameterSweep.objects.select_related("strategy")
        .prefetch_related("symbols")
        .order_by("-created_at")
        .first()
    )

    context["bt_recent_runs"] = list(
        BacktestRun.objects.select_related("strategy", "metrics")
        .prefetch_related("symbols")
        .order_by("-created_at")[:6]
    )

    return context

"""Server-rendered HTML views for runs (list + detail)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import BacktestRun, Trade


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
        BacktestRun.objects.select_related("strategy", "metrics").prefetch_related("symbols"),
        id=run_id,
    )
    trades = list(
        Trade.objects.filter(run=run).select_related("symbol").order_by("entry_ts")[:500]
    )
    return render(request, "runs/detail.html", {"run": run, "trades": trades})

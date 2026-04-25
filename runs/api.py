"""DRF ViewSets and routing for the runs app."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import BacktestRun, EquityPoint, Strategy, Trade
from .serializers import (
    BacktestRunCreateSerializer,
    BacktestRunDetailSerializer,
    BacktestRunListSerializer,
    EquityPointSerializer,
    StrategyDetailSerializer,
    StrategySerializer,
    TradeSerializer,
)
from .tasks import run_backtest


class StrategyViewSet(viewsets.ModelViewSet):
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer
    lookup_field = "slug"
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["name", "updated_at"]

    def get_serializer_class(self):
        if self.action in {"retrieve", "create", "update", "partial_update"}:
            return StrategyDetailSerializer
        return StrategySerializer


class BacktestRunViewSet(viewsets.ModelViewSet):
    queryset = (
        BacktestRun.objects.select_related("strategy", "metrics")
        .prefetch_related("symbols")
        .all()
    )
    filterset_fields = ["status", "strategy", "timeframe"]
    search_fields = ["strategy__name", "strategy__slug"]
    ordering_fields = ["created_at", "started_at", "finished_at", "duration_ms"]

    def get_serializer_class(self):
        if self.action == "create":
            return BacktestRunCreateSerializer
        if self.action == "list":
            return BacktestRunListSerializer
        return BacktestRunDetailSerializer

    def create(self, request, *args, **kwargs):  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save(created_by=request.user if request.user.is_authenticated else None)
        run_backtest.delay(run.id)
        detail = BacktestRunDetailSerializer(run)
        return Response(detail.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def rerun(self, request, pk=None):  # noqa: ARG002
        run = self.get_object()
        run_backtest.delay(run.id)
        return Response(
            {"run_id": run.id, "status": "queued"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="trades")
    def trades(self, request, pk=None):  # noqa: ARG002
        qs = Trade.objects.filter(run_id=pk).select_related("symbol").order_by("entry_ts")
        return Response(TradeSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path="equity-curve")
    def equity_curve(self, request, pk=None):  # noqa: ARG002
        qs = EquityPoint.objects.filter(run_id=pk).order_by("ts")
        return Response(EquityPointSerializer(qs, many=True).data)

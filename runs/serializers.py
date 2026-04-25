"""DRF serializers for the runs app."""

from __future__ import annotations

from rest_framework import serializers

from bars.models import Symbol

from .models import BacktestRun, EquityPoint, RunMetrics, Strategy, Trade


class SymbolMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symbol
        fields = ["id", "ticker", "name", "asset_class"]


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "entrypoint",
            "params_schema",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StrategyDetailSerializer(StrategySerializer):
    class Meta(StrategySerializer.Meta):
        fields = StrategySerializer.Meta.fields + ["code"]


class TradeSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source="symbol.ticker", read_only=True)

    class Meta:
        model = Trade
        fields = [
            "id",
            "symbol",
            "side",
            "qty",
            "entry_ts",
            "entry_price",
            "exit_ts",
            "exit_price",
            "pnl",
            "return_pct",
            "commission_paid",
            "duration_seconds",
            "tag",
        ]
        read_only_fields = fields


class EquityPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquityPoint
        fields = ["ts", "equity", "drawdown_pct", "drawdown_duration_days"]
        read_only_fields = fields


class RunMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RunMetrics
        fields = [
            "return_pct",
            "buy_hold_return_pct",
            "annualized_return_pct",
            "cagr_pct",
            "volatility_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "max_drawdown_pct",
            "avg_drawdown_pct",
            "max_drawdown_duration_days",
            "trade_count",
            "win_rate_pct",
            "best_trade_pct",
            "worst_trade_pct",
            "avg_trade_pct",
            "profit_factor",
            "expectancy_pct",
            "sqn",
            "kelly_criterion",
            "exposure_time_pct",
            "final_equity",
            "peak_equity",
            "commissions_paid",
        ]
        read_only_fields = fields


class BacktestRunListSerializer(serializers.ModelSerializer):
    strategy = serializers.CharField(source="strategy.name", read_only=True)
    strategy_slug = serializers.CharField(source="strategy.slug", read_only=True)
    symbols = serializers.SerializerMethodField()
    return_pct = serializers.SerializerMethodField()
    sharpe_ratio = serializers.SerializerMethodField()

    class Meta:
        model = BacktestRun
        fields = [
            "id",
            "strategy",
            "strategy_slug",
            "symbols",
            "timeframe",
            "start_date",
            "end_date",
            "initial_capital",
            "params",
            "status",
            "duration_ms",
            "return_pct",
            "sharpe_ratio",
            "created_at",
        ]
        read_only_fields = fields

    def get_symbols(self, obj: BacktestRun) -> list[str]:
        return [s.ticker for s in obj.symbols.all()]

    def get_return_pct(self, obj: BacktestRun):
        return getattr(getattr(obj, "metrics", None), "return_pct", None)

    def get_sharpe_ratio(self, obj: BacktestRun):
        return getattr(getattr(obj, "metrics", None), "sharpe_ratio", None)


class BacktestRunCreateSerializer(serializers.ModelSerializer):
    strategy = serializers.SlugRelatedField(slug_field="slug", queryset=Strategy.objects.all())
    symbols = serializers.SlugRelatedField(
        slug_field="ticker",
        queryset=Symbol.objects.filter(is_active=True),
        many=True,
    )

    class Meta:
        model = BacktestRun
        fields = [
            "id",
            "strategy",
            "symbols",
            "timeframe",
            "start_date",
            "end_date",
            "initial_capital",
            "commission_bps",
            "slippage_bps",
            "params",
        ]
        read_only_fields = ["id"]


class BacktestRunDetailSerializer(serializers.ModelSerializer):
    strategy = StrategySerializer(read_only=True)
    symbols = SymbolMiniSerializer(many=True, read_only=True)
    metrics = RunMetricsSerializer(read_only=True)

    class Meta:
        model = BacktestRun
        fields = [
            "id",
            "strategy",
            "symbols",
            "timeframe",
            "start_date",
            "end_date",
            "initial_capital",
            "commission_bps",
            "slippage_bps",
            "params",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "error",
            "metrics",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

from django.contrib import admin

from .models import BacktestRun, EquityPoint, ParameterSweep, RunMetrics, Strategy, Trade
from .tasks import optimize


class TradeInline(admin.TabularInline):
    model = Trade
    extra = 0
    can_delete = False
    readonly_fields = (
        "symbol",
        "side",
        "qty",
        "entry_ts",
        "entry_price",
        "exit_ts",
        "exit_price",
        "pnl",
        "return_pct",
        "duration_seconds",
        "tag",
    )
    raw_id_fields = ("symbol",)


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "user", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "strategy",
        "status",
        "start_date",
        "end_date",
        "initial_capital",
        "duration_ms",
        "created_at",
    )
    list_filter = ("status", "strategy", "timeframe")
    search_fields = ("strategy__name", "strategy__slug")
    date_hierarchy = "created_at"
    raw_id_fields = ("strategy", "created_by")
    filter_horizontal = ("symbols",)
    readonly_fields = ("started_at", "finished_at", "duration_ms", "error", "created_at", "updated_at")
    inlines = [TradeInline]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "run",
        "symbol",
        "side",
        "qty",
        "entry_ts",
        "exit_ts",
        "pnl",
        "return_pct",
    )
    list_filter = ("side", "symbol")
    search_fields = ("run__id", "symbol__ticker", "tag")
    raw_id_fields = ("run", "symbol")


@admin.register(EquityPoint)
class EquityPointAdmin(admin.ModelAdmin):
    list_display = ("run", "ts", "equity", "drawdown_pct")
    list_filter = ("run",)
    raw_id_fields = ("run",)
    date_hierarchy = "ts"


@admin.register(RunMetrics)
class RunMetricsAdmin(admin.ModelAdmin):
    list_display = (
        "run",
        "return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "trade_count",
        "win_rate_pct",
    )
    raw_id_fields = ("run",)


@admin.register(ParameterSweep)
class ParameterSweepAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "strategy",
        "status",
        "children_total",
        "children_succeeded",
        "children_failed",
        "duration_ms",
        "created_at",
    )
    list_filter = ("status", "strategy")
    raw_id_fields = ("strategy", "created_by")
    filter_horizontal = ("symbols",)
    readonly_fields = (
        "started_at",
        "finished_at",
        "duration_ms",
        "children_total",
        "children_succeeded",
        "children_failed",
        "error",
        "created_at",
        "updated_at",
    )
    actions = ["queue_sweep"]

    @admin.action(description="Queue / re-queue selected sweeps")
    def queue_sweep(self, request, queryset):
        for sweep in queryset:
            optimize.delay(sweep.id)
        self.message_user(request, f"Queued {queryset.count()} sweep(s).")

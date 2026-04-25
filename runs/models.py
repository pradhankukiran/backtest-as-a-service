from django.conf import settings
from django.db import models

from bars.models import Symbol, TimestampedModel


class Strategy(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="strategies",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    code = models.TextField(help_text="Python source defining the Strategy class.")
    entrypoint = models.CharField(
        max_length=120,
        default="Strategy",
        help_text="Class name to load from the code body.",
    )
    params_schema = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "strategies"

    def __str__(self) -> str:
        return self.name


class ParameterSweep(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    strategy = models.ForeignKey(Strategy, on_delete=models.PROTECT, related_name="sweeps")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parameter_sweeps",
    )
    symbols = models.ManyToManyField(Symbol, related_name="sweeps")
    timeframe = models.CharField(max_length=8, default="1d")
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.DecimalField(max_digits=18, decimal_places=2, default=10000)
    commission_bps = models.PositiveIntegerField(default=20)
    slippage_bps = models.PositiveIntegerField(default=0)
    base_params = models.JSONField(default=dict, blank=True)
    grid = models.JSONField(
        default=dict,
        help_text='{"param_name": [v1, v2, v3]} or {"param_name": {"start":5,"stop":30,"step":5}}',
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    children_total = models.PositiveIntegerField(default=0)
    children_succeeded = models.PositiveIntegerField(default=0)
    children_failed = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self) -> str:
        return f"Sweep #{self.id} {self.strategy.name} ({self.status})"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("sweep-detail", args=[self.id])


class BacktestRun(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    strategy = models.ForeignKey(Strategy, on_delete=models.PROTECT, related_name="runs")
    sweep = models.ForeignKey(
        ParameterSweep,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backtest_runs",
    )
    symbols = models.ManyToManyField(Symbol, related_name="runs")
    timeframe = models.CharField(max_length=8, default="1d")
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.DecimalField(max_digits=18, decimal_places=2, default=10000)
    commission_bps = models.PositiveIntegerField(
        default=20,
        help_text="Commission in basis points (1 bps = 0.01%).",
    )
    slippage_bps = models.PositiveIntegerField(default=0)
    params = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["strategy", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.strategy.name} #{self.id} ({self.status})"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("run-detail", args=[self.id])


class Trade(models.Model):
    class Side(models.TextChoices):
        LONG = "long", "Long"
        SHORT = "short", "Short"

    run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="trades")
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name="+")
    side = models.CharField(max_length=8, choices=Side.choices, default=Side.LONG)
    qty = models.DecimalField(max_digits=24, decimal_places=8)
    entry_ts = models.DateTimeField()
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    exit_ts = models.DateTimeField(null=True, blank=True)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    return_pct = models.FloatField(null=True, blank=True)
    commission_paid = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    duration_seconds = models.BigIntegerField(null=True, blank=True)
    tag = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["run", "entry_ts"]
        indexes = [
            models.Index(fields=["run", "entry_ts"]),
            models.Index(fields=["symbol", "-entry_ts"]),
        ]

    def __str__(self) -> str:
        return f"Trade run={self.run_id} {self.symbol.ticker} {self.side} qty={self.qty}"


class EquityPoint(models.Model):
    run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="equity_points")
    ts = models.DateTimeField()
    equity = models.DecimalField(max_digits=20, decimal_places=8)
    drawdown_pct = models.FloatField(null=True, blank=True)
    drawdown_duration_days = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["run", "ts"]
        indexes = [
            models.Index(fields=["run", "ts"]),
        ]

    def __str__(self) -> str:
        return f"Equity run={self.run_id} ts={self.ts:%Y-%m-%d} eq={self.equity}"


class RunMetrics(TimestampedModel):
    run = models.OneToOneField(BacktestRun, on_delete=models.CASCADE, related_name="metrics")

    return_pct = models.FloatField(null=True, blank=True)
    buy_hold_return_pct = models.FloatField(null=True, blank=True)
    annualized_return_pct = models.FloatField(null=True, blank=True)
    cagr_pct = models.FloatField(null=True, blank=True)
    volatility_pct = models.FloatField(null=True, blank=True)

    sharpe_ratio = models.FloatField(null=True, blank=True)
    sortino_ratio = models.FloatField(null=True, blank=True)
    calmar_ratio = models.FloatField(null=True, blank=True)
    alpha_pct = models.FloatField(null=True, blank=True)
    beta = models.FloatField(null=True, blank=True)

    max_drawdown_pct = models.FloatField(null=True, blank=True)
    avg_drawdown_pct = models.FloatField(null=True, blank=True)
    max_drawdown_duration_days = models.FloatField(null=True, blank=True)
    avg_drawdown_duration_days = models.FloatField(null=True, blank=True)

    trade_count = models.IntegerField(default=0)
    win_rate_pct = models.FloatField(null=True, blank=True)
    best_trade_pct = models.FloatField(null=True, blank=True)
    worst_trade_pct = models.FloatField(null=True, blank=True)
    avg_trade_pct = models.FloatField(null=True, blank=True)
    profit_factor = models.FloatField(null=True, blank=True)
    expectancy_pct = models.FloatField(null=True, blank=True)
    sqn = models.FloatField(null=True, blank=True)
    kelly_criterion = models.FloatField(null=True, blank=True)

    final_equity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    peak_equity = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    commissions_paid = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exposure_time_pct = models.FloatField(null=True, blank=True)

    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "run metrics"

    def __str__(self) -> str:
        return f"Metrics run={self.run_id}"

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Symbol(TimestampedModel):
    class AssetClass(models.TextChoices):
        EQUITY = "equity", "Equity"
        ETF = "etf", "ETF"
        CRYPTO = "crypto", "Crypto"
        FX = "fx", "Forex"
        FUTURE = "future", "Future"
        INDEX = "index", "Index"

    ticker = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=200, blank=True)
    exchange = models.CharField(max_length=32, blank=True)
    asset_class = models.CharField(
        max_length=20,
        choices=AssetClass.choices,
        default=AssetClass.EQUITY,
    )
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self) -> str:
        return self.ticker


class Bar(TimestampedModel):
    class Timeframe(models.TextChoices):
        DAY = "1d", "1 Day"
        HOUR = "1h", "1 Hour"
        FIFTEEN_MIN = "15m", "15 Minutes"
        FIVE_MIN = "5m", "5 Minutes"
        ONE_MIN = "1m", "1 Minute"

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="bars")
    ts = models.DateTimeField(db_index=True)
    timeframe = models.CharField(
        max_length=8,
        choices=Timeframe.choices,
        default=Timeframe.DAY,
    )
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "ts", "timeframe"],
                name="uq_bar_per_symbol_ts_tf",
            ),
        ]
        indexes = [
            models.Index(fields=["symbol", "-ts"]),
            models.Index(fields=["timeframe", "-ts"]),
        ]
        ordering = ["symbol", "-ts"]

    def __str__(self) -> str:
        return f"{self.symbol.ticker} {self.timeframe} @ {self.ts:%Y-%m-%d %H:%M}"

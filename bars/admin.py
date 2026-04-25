from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Bar, Symbol
from .tasks import ingest_bars


@admin.register(Symbol)
class SymbolAdmin(ModelAdmin):
    list_display = ("ticker", "name", "exchange", "asset_class", "currency", "is_active")
    list_filter = ("asset_class", "is_active", "exchange")
    search_fields = ("ticker", "name")
    ordering = ("ticker",)
    actions = ["queue_ingest_recent", "queue_ingest_one_year"]

    @admin.action(description="Ingest last 30 days of bars")
    def queue_ingest_recent(self, request, queryset):
        for symbol in queryset:
            ingest_bars.delay(symbol.ticker, days_back=30)
        self.message_user(request, f"Queued ingest for {queryset.count()} symbol(s).")

    @admin.action(description="Backfill last 365 days of bars")
    def queue_ingest_one_year(self, request, queryset):
        for symbol in queryset:
            ingest_bars.delay(symbol.ticker, days_back=365)
        self.message_user(request, f"Queued 365d backfill for {queryset.count()} symbol(s).")


@admin.register(Bar)
class BarAdmin(ModelAdmin):
    list_display = ("symbol", "ts", "timeframe", "open", "high", "low", "close", "volume")
    list_filter = ("timeframe", "symbol")
    search_fields = ("symbol__ticker",)
    date_hierarchy = "ts"
    raw_id_fields = ("symbol",)
    ordering = ("symbol", "-ts")

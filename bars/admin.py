from django.contrib import admin

from .models import Bar, Symbol


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ("ticker", "name", "exchange", "asset_class", "currency", "is_active")
    list_filter = ("asset_class", "is_active", "exchange")
    search_fields = ("ticker", "name")
    ordering = ("ticker",)


@admin.register(Bar)
class BarAdmin(admin.ModelAdmin):
    list_display = ("symbol", "ts", "timeframe", "open", "high", "low", "close", "volume")
    list_filter = ("timeframe", "symbol")
    search_fields = ("symbol__ticker",)
    date_hierarchy = "ts"
    raw_id_fields = ("symbol",)
    ordering = ("symbol", "-ts")

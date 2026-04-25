"""DRF ViewSets for the bars app."""

from __future__ import annotations

from rest_framework import serializers, viewsets

from .models import Bar, Symbol


class SymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symbol
        fields = [
            "id",
            "ticker",
            "name",
            "exchange",
            "asset_class",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        ]


class BarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bar
        fields = ["id", "symbol", "ts", "timeframe", "open", "high", "low", "close", "volume"]
        read_only_fields = fields


class SymbolViewSet(viewsets.ModelViewSet):
    queryset = Symbol.objects.all()
    serializer_class = SymbolSerializer
    lookup_field = "ticker"
    filterset_fields = ["asset_class", "is_active", "exchange"]
    search_fields = ["ticker", "name"]
    ordering_fields = ["ticker", "asset_class", "updated_at"]


class BarViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Bar.objects.select_related("symbol").all()
    serializer_class = BarSerializer
    filterset_fields = ["symbol", "timeframe"]
    ordering_fields = ["ts", "symbol"]

"""Management command to ingest historical bars synchronously.

Usage:
    python manage.py ingest_bars AAPL MSFT --start 2020-01-01 --end 2024-01-01
    python manage.py ingest_bars AAPL --days-back 90
    python manage.py ingest_bars --all --days-back 5     # every active symbol
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from bars.ingestion import ingest_symbol
from bars.models import Symbol


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class Command(BaseCommand):
    help = "Ingest OHLCV bars from yfinance for one or more tickers."

    def add_arguments(self, parser):
        parser.add_argument(
            "tickers",
            nargs="*",
            help="Tickers to ingest (skip with --all to use every active Symbol).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all_symbols",
            help="Ingest every active Symbol.",
        )
        parser.add_argument(
            "--start",
            type=_parse_date,
            help="Start date (YYYY-MM-DD). Mutually exclusive with --days-back.",
        )
        parser.add_argument(
            "--end",
            type=_parse_date,
            help="End date (YYYY-MM-DD). Defaults to now.",
        )
        parser.add_argument(
            "--days-back",
            type=int,
            help="Lookback window in days from now. Mutually exclusive with --start.",
        )
        parser.add_argument(
            "--timeframe",
            default="1d",
            help="Timeframe (default: 1d).",
        )
        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Auto-create Symbol rows for tickers that don't exist yet.",
        )

    def handle(self, *tickers, **options):  # noqa: ARG002
        provided_tickers = list(options["tickers"])
        all_symbols = options["all_symbols"]
        start = options["start"]
        end = options["end"]
        days_back = options["days_back"]
        timeframe = options["timeframe"]
        create_missing = options["create_missing"]

        if start and days_back:
            raise CommandError("--start and --days-back are mutually exclusive.")
        if not provided_tickers and not all_symbols:
            raise CommandError("Pass at least one ticker or --all.")

        if all_symbols:
            symbols = list(Symbol.objects.filter(is_active=True))
        else:
            symbols = []
            for ticker in provided_tickers:
                try:
                    symbols.append(Symbol.objects.get(ticker=ticker.upper()))
                except Symbol.DoesNotExist:
                    if create_missing:
                        symbols.append(Symbol.objects.create(ticker=ticker.upper()))
                        self.stdout.write(f"created Symbol {ticker.upper()}")
                    else:
                        raise CommandError(
                            f"Symbol {ticker} does not exist. Pass --create-missing to autocreate."
                        ) from None

        for symbol in symbols:
            self.stdout.write(f"ingesting {symbol.ticker} ({timeframe}) ...")
            result = ingest_symbol(
                symbol,
                start=start,
                end=end,
                days_back=days_back,
                timeframe=timeframe,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  fetched={result.fetched} upserted={result.upserted} "
                    f"earliest={result.earliest} latest={result.latest}"
                )
            )

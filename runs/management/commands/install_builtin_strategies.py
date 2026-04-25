"""Install the bundled example strategies into the Strategy table.

Idempotent: re-running updates existing rows in place.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from runs.models import Strategy
from runs.strategies.builtin import BUILTINS


class Command(BaseCommand):
    help = "Install / refresh built-in example strategies."

    def handle(self, *args, **options):  # noqa: ARG002
        for builtin in BUILTINS:
            obj, created = Strategy.objects.update_or_create(
                slug=builtin.slug,
                defaults={
                    "name": builtin.name,
                    "description": builtin.description,
                    "entrypoint": builtin.entrypoint,
                    "code": builtin.code,
                    "params_schema": builtin.params_schema,
                    "is_active": True,
                },
            )
            verb = "created" if created else "updated"
            self.stdout.write(self.style.SUCCESS(f"  {verb} strategy {obj.slug}"))

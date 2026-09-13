"""
Bring already-stored images up to the current pipeline.

The derivatives an asset carries are whatever the pipeline produced on the day
it was uploaded. A shop that has been running for a year has images with no
AVIF and full-size originals nobody renders — the saving only reaches them if
something goes back over what is already there.

Safe to run repeatedly and safe to interrupt: each asset is processed on its
own, and `generate_image_derivatives` writes the new files before it removes
the old one.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.media.models import AssetKind, MediaAsset


class Command(BaseCommand):
    help = "Regenerate derivatives and shrink stored masters for existing images."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--tenant",
            help="Slug of a single tenant. Omitted, every tenant is processed.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many assets. Useful for a first look.",
        )
        parser.add_argument(
            "--missing-avif",
            action="store_true",
            help="Only assets that have no AVIF derivatives yet.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be processed without touching anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.media.tasks import generate_image_derivatives

        queryset = MediaAsset.objects.filter(kind=AssetKind.IMAGE).order_by("created_at")

        if options["tenant"]:
            queryset = queryset.filter(tenant__slug=options["tenant"])

        if options["missing_avif"]:
            # Cheaper than a JSON query and clear about what it means: an asset
            # is stale when nothing in its derivatives is an AVIF entry.
            stale = [
                asset.pk
                for asset in queryset.only("pk", "derivatives")
                if not any(str(name).startswith("avif_") for name in (asset.derivatives or {}))
            ]
            queryset = MediaAsset.objects.filter(pk__in=stale).order_by("created_at")

        if options["limit"]:
            queryset = queryset[: options["limit"]]

        assets = list(queryset)
        before = sum(asset.size_bytes for asset in assets)

        if options["dry_run"]:
            self.stdout.write(
                f"{len(assets)} images, {before:,} bytes of masters (nothing written)"
            )
            return

        processed = 0
        failed = 0

        for asset in assets:
            try:
                generate_image_derivatives(str(asset.pk))
                processed += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f"  {asset.pk}: {exc}")

        after = sum(
            MediaAsset.objects.filter(pk__in=[a.pk for a in assets]).values_list(
                "size_bytes", flat=True
            )
        )
        saved = before - after

        self.stdout.write(
            self.style.SUCCESS(
                f"{processed} processed, {failed} failed. "
                f"Masters {before:,} -> {after:,} bytes ({saved:,} saved)"
            )
        )

"""
Deleting orphans without deleting the things in use.

`cleanup_orphaned_assets` decides what gets removed from the bucket, and it
listed the relations that count as "in use" by hand. That list had fallen two
behind the model — `brand_logos` and `report_jobs` were added later — so a
brand's logo and a merchant's downloadable report were both collectable as
orphans once they were a day old.

It never happened, only because the task was never scheduled. Wiring it up
without fixing this would have started deleting live files on a timer.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.media.models import MediaAsset
from apps.media.tasks import _unreferenced, cleanup_orphaned_assets

pytestmark = pytest.mark.django_db


def make_asset(tenant: Any, *, age_hours: int = 48, key: str = "a") -> MediaAsset:
    """An asset old enough for the cleanup to consider it."""
    asset = MediaAsset.objects.create(
        tenant=tenant,
        kind="IMAGE",
        storage_key=f"test/{key}.png",
        original_filename=f"{key}.png",
        content_type="image/png",
        size_bytes=10,
    )
    # `created_at` is auto_now_add, so it has to be moved after the fact.
    MediaAsset.objects.filter(pk=asset.pk).update(
        created_at=timezone.now() - timedelta(hours=age_hours)
    )
    asset.refresh_from_db()
    return asset


class TestGuardCoversTheModel:
    def test_every_relation_is_guarded(self) -> None:
        """Derived from `_meta`, so a relation added tomorrow is covered too.

        The point of this test is that it cannot be satisfied by remembering to
        update a list — it compares the filter against the model itself.
        """
        guarded = {str(child[0]).removesuffix("__isnull") for child in _unreferenced().children}
        relations = {
            field.get_accessor_name()
            for field in MediaAsset._meta.get_fields()
            if field.auto_created and not field.concrete
        }

        assert guarded == relations

    def test_the_two_that_were_missing_are_included(self) -> None:
        """Named explicitly, because these are the ones that were deletable."""
        guarded = {str(child[0]) for child in _unreferenced().children}

        assert "brand_logos__isnull" in guarded
        assert "report_jobs__isnull" in guarded


class TestCleanupBehaviour:
    def test_an_unattached_asset_is_removed(self, tenant: Any) -> None:
        orphan = make_asset(tenant, key="orphan")

        assert cleanup_orphaned_assets() == 1
        assert not MediaAsset.objects.filter(pk=orphan.pk).exists()

    def test_a_brand_logo_survives(self, tenant: Any) -> None:
        """The exact file the old hand-written filter would have deleted."""
        from apps.catalog.models import Brand

        asset = make_asset(tenant, key="logo")
        Brand.objects.create(tenant=tenant, name="Marca", slug="marca", logo=asset)

        assert cleanup_orphaned_assets() == 0
        assert MediaAsset.objects.filter(pk=asset.pk).exists()

    def test_a_recent_asset_is_left_alone(self, tenant: Any) -> None:
        """An upload in progress is not an orphan yet."""
        fresh = make_asset(tenant, age_hours=1, key="fresh")

        assert cleanup_orphaned_assets() == 0
        assert MediaAsset.objects.filter(pk=fresh.pk).exists()

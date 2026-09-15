"""
Add the `back_soon` rail to layouts that were stored before it existed.

Without this, every shop created before this deploy keeps a five-rail layout.
Two things then break, and neither is obvious:

* the rail never renders, because the home endpoint iterates the *stored* list
  and falls back to the default only when nothing is stored at all;
* saving the layout starts failing. The serializer requires every known section
  to be present exactly once, so the dashboard would load five, submit five, and
  be told one is missing — with no way for the merchant to add it.

Appended at the end and switched off. On is the default for a *new* shop, which
is choosing the feature; silently changing the front page of a shop that already
exists is not the same decision.

Reversible: the down migration strips the key again, so rolling back the code
does not leave layouts the old validator would reject.
"""

from __future__ import annotations

from django.db import migrations

SECTION_KEY = "back_soon"


def add_section(apps, schema_editor):
    TenantSettings = apps.get_model("tenants", "TenantSettings")

    for row in TenantSettings.objects.exclude(home_layout=None).iterator():
        layout = row.home_layout
        if not isinstance(layout, list) or not layout:
            continue
        if any(isinstance(s, dict) and s.get("key") == SECTION_KEY for s in layout):
            continue

        layout.append({"key": SECTION_KEY, "enabled": False, "title": "", "limit": 8})
        row.home_layout = layout
        row.save(update_fields=["home_layout"])


def remove_section(apps, schema_editor):
    TenantSettings = apps.get_model("tenants", "TenantSettings")

    for row in TenantSettings.objects.exclude(home_layout=None).iterator():
        layout = row.home_layout
        if not isinstance(layout, list):
            continue

        kept = [s for s in layout if not (isinstance(s, dict) and s.get("key") == SECTION_KEY)]
        if len(kept) != len(layout):
            row.home_layout = kept
            row.save(update_fields=["home_layout"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0008_tenantsettings_hide_out_of_stock"),
    ]

    operations = [
        migrations.RunPython(add_section, remove_section),
    ]

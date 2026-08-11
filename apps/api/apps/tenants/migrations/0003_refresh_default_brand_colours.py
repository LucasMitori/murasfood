"""Move tenants still on the old default palette onto the new one.

Only rows holding the *exact* previous defaults are touched. A merchant who
deliberately picked a colour keeps it; the ones being corrected here are those
that were never customised and would otherwise show a palette the product no
longer ships.
"""

from django.db import migrations

OLD_TO_NEW = {
    "primary_color": ("#7B2D3B", "#8C1425"),
    "secondary_color": ("#2E2A2B", "#211E1F"),
    "accent_color": ("#A64253", "#B02233"),
    "dark_primary_color": ("#E8C9CF", "#E2495D"),
}


def refresh(apps, schema_editor):
    branding_model = apps.get_model("tenants", "TenantBranding")

    for field, (old, new) in OLD_TO_NEW.items():
        branding_model.objects.filter(**{field: old}).update(**{field: new})


def restore(apps, schema_editor):
    branding_model = apps.get_model("tenants", "TenantBranding")

    for field, (old, new) in OLD_TO_NEW.items():
        branding_model.objects.filter(**{field: new}).update(**{field: old})


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_alter_tenantbranding_accent_color_and_more"),
    ]

    operations = [
        migrations.RunPython(refresh, restore),
    ]

"""Seed demo hero banners.

The images are generated here rather than downloaded or committed. A
white-label codebase must not carry a real merchant's photography, and a seed
that reaches out to the network fails on the first machine without it.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.media.models import AssetFolder, Banner
from apps.media.services import store_upload
from apps.tenants.models import Tenant

WIDTH, HEIGHT = 1920, 1080

#: Placeholder artwork, deliberately abstract. Each entry is a gradient pair
#: plus the wording and layout the merchant would set for themselves.
BANNERS: tuple[dict[str, Any], ...] = (
    {
        "title": "Feira fresca todo dia",
        "subtitle": "Hortifrúti selecionado",
        "cta_label": "Ver hortifrúti",
        "text_align": Banner.TextAlign.LEFT,
        "overlay_opacity": 55,
        "link_type": Banner.LinkType.CATEGORY,
        "link_target": "hortifruti",
        "priority": 30,
        "from_rgb": (28, 62, 42),
        "to_rgb": (96, 140, 74),
    },
    {
        "title": "Ofertas da semana",
        "subtitle": "Até 30% de desconto",
        "cta_label": "Ver ofertas",
        "text_align": Banner.TextAlign.CENTER,
        "overlay_opacity": 45,
        "link_type": Banner.LinkType.PROMOTION,
        "link_target": "",
        "priority": 20,
        "from_rgb": (74, 10, 22),
        "to_rgb": (168, 40, 58),
    },
    {
        "title": "Padaria quentinha",
        "subtitle": "Assados várias vezes ao dia",
        "cta_label": "Ver padaria",
        "text_align": Banner.TextAlign.RIGHT,
        "overlay_opacity": 50,
        "link_type": Banner.LinkType.CATEGORY,
        "link_target": "padaria",
        "priority": 10,
        "from_rgb": (58, 38, 18),
        "to_rgb": (150, 106, 52),
    },
)


def _gradient_image(from_rgb: tuple[int, int, int], to_rgb: tuple[int, int, int]) -> bytes:
    """A diagonal gradient with a soft vignette, as a JPEG."""
    from PIL import Image

    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()

    # Sampled on a coarse grid and then resized: computing 2M pixels in Python
    # takes seconds, and the gradient is smooth enough that nobody can tell.
    step = 8
    for x in range(0, WIDTH, step):
        for y in range(0, HEIGHT, step):
            ratio = (x / WIDTH * 0.65) + (y / HEIGHT * 0.35)
            # Darken towards the corners so overlaid text keeps its contrast.
            vignette = 1 - 0.28 * math.hypot(x / WIDTH - 0.5, y / HEIGHT - 0.5)
            colour = tuple(
                int((from_rgb[i] + (to_rgb[i] - from_rgb[i]) * ratio) * vignette) for i in range(3)
            )
            for dx in range(step):
                for dy in range(step):
                    if x + dx < WIDTH and y + dy < HEIGHT:
                        pixels[x + dx, y + dy] = colour

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Create demo hero banners for the storefront home page."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", default="demo", help="Tenant slug to seed.")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing banners first instead of skipping.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant '{options['tenant']}' not found."))
            return

        existing = Banner.objects.filter(tenant=tenant)
        if options["replace"]:
            count = existing.count()
            existing.delete()
            self.stdout.write(f"Removed {count} existing banner(s).")
        elif existing.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"{existing.count()} banner(s) already exist; pass --replace to recreate."
                )
            )
            return

        for spec in BANNERS:
            payload = _gradient_image(spec["from_rgb"], spec["to_rgb"])
            upload = SimpleUploadedFile(
                f"banner-{spec['link_target'] or 'ofertas'}.jpg",
                payload,
                content_type="image/jpeg",
            )

            asset = store_upload(
                tenant=tenant,
                upload=upload,
                folder=AssetFolder.BANNER,
                alt_text=spec["title"],
            )

            Banner.objects.create(
                tenant=tenant,
                image=asset,
                title=spec["title"],
                subtitle=spec["subtitle"],
                cta_label=spec["cta_label"],
                text_align=spec["text_align"],
                overlay_opacity=spec["overlay_opacity"],
                link_type=spec["link_type"],
                link_target=spec["link_target"],
                priority=spec["priority"],
                is_active=True,
            )
            self.stdout.write(f"  + {spec['title']}")

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(BANNERS)} banners."))

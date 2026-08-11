"""Generate placeholder artwork for seeded products and categories.

Abstract tiles, generated here. A white-label codebase must not ship a real
merchant's product photography, and a seed that downloads images fails on the
first machine without a network. Each tile is tinted by category so a grid of
them still reads as a shop rather than a wall of identical grey.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Product, ProductImage
from apps.media.models import AssetFolder
from apps.media.services import store_upload
from apps.tenants.models import Tenant

SIZE = 800

#: Category slug -> (background, accent). Muted on purpose: the tiles sit
#: behind red price tags and must not compete with them.
PALETTE: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "padaria": ((238, 226, 205), (176, 137, 84)),
    "hortifruti": ((225, 236, 219), (108, 152, 86)),
    "acougue": ((240, 220, 219), (170, 89, 88)),
    "laticinios": ((240, 236, 224), (191, 168, 108)),
    "mercearia": ((233, 229, 224), (140, 124, 106)),
    "bebidas": ((219, 230, 240), (94, 136, 175)),
    "limpeza": ((219, 236, 238), (86, 148, 155)),
    "higiene": ((231, 226, 240), (129, 112, 172)),
}
DEFAULT_PALETTE = ((234, 230, 229), (135, 125, 124))


def _initials(name: str) -> str:
    parts = [word for word in name.split() if word[:1].isalpha()]
    return "".join(word[0] for word in parts[:2]).upper() or "?"


def _tile(name: str, slug: str) -> bytes:
    """A soft radial tile carrying the item's initials."""
    from PIL import Image, ImageDraw, ImageFont

    background, accent = PALETTE.get(slug, DEFAULT_PALETTE)
    image = Image.new("RGB", (SIZE, SIZE), background)
    pixels = image.load()

    # Coarse grid, same reasoning as the banner seed: per-pixel Python over
    # 640k pixels is slow and the gradient is smooth enough that it never shows.
    step = 8
    centre = SIZE / 2
    for x in range(0, SIZE, step):
        for y in range(0, SIZE, step):
            distance = math.hypot(x - centre, y - centre) / centre
            weight = max(0.0, 1 - distance) * 0.35
            colour = tuple(
                int(background[i] + (accent[i] - background[i]) * weight) for i in range(3)
            )
            for dx in range(step):
                for dy in range(step):
                    if x + dx < SIZE and y + dy < SIZE:
                        pixels[x + dx, y + dy] = colour

    draw = ImageDraw.Draw(image)
    text = _initials(name)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 220)
    except OSError:
        # Pillow always ships a bitmap fallback; the tile is still usable.
        font = ImageFont.load_default()

    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((SIZE - (box[2] - box[0])) / 2 - box[0], (SIZE - (box[3] - box[1])) / 2 - box[1]),
        text,
        font=font,
        fill=tuple(int(channel * 0.72) for channel in accent),
    )

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=84, optimize=True)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Generate placeholder images for seeded products and categories."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", default="demo")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Regenerate for items that already have an image.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant '{options['tenant']}' not found."))
            return

        replace = options["replace"]
        categories = 0
        products = 0

        for category in Category.objects.filter(tenant=tenant).select_related("parent"):
            if category.image_id and not replace:
                continue
            asset = self._store(tenant, category.name, category.slug)
            category.image = asset
            category.save(update_fields=["image", "updated_at"])
            categories += 1

        queryset = Product.objects.filter(tenant=tenant).select_related("category")
        for product in queryset:
            if product.images.exists() and not replace:
                continue

            slug = product.category.slug if product.category else ""
            asset = self._store(tenant, product.name, slug)
            ProductImage.objects.create(
                tenant=tenant, product=product, asset=asset, position=0, is_primary=True
            )
            products += 1

        self.stdout.write(
            self.style.SUCCESS(f"Generated {categories} category and {products} product images.")
        )

    def _store(self, tenant: Tenant, name: str, slug: str) -> Any:
        upload = SimpleUploadedFile(
            f"{slug or 'item'}-{abs(hash(name)) % 10**8}.jpg",
            _tile(name, slug),
            content_type="image/jpeg",
        )
        return store_upload(tenant=tenant, upload=upload, folder=AssetFolder.PRODUCT, alt_text=name)

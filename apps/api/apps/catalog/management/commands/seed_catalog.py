"""
Seed a 50-product catalog.

Replaces whatever catalog exists with a broad, obviously fictitious assortment
spanning eight sections, mixing unit-priced and weight-priced goods so the
storefront exercises both quantity models (spec §8, §91).

Each product also gets a short price history so the product page's price chart
has something real to plot rather than a single point.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

# (name, section, unit, price, cost, stock, weighted, featured)
CATALOG: tuple[tuple[str, str, str, str, str, str, bool, bool], ...] = (
    # --- Padaria -------------------------------------------------------------
    ("Pão Francês Fictício", "padaria", "kg", "18.90", "10.40", "42.500", True, True),
    ("Pão de Forma Integral Demo", "padaria", "un", "9.80", "5.60", "60", False, False),
    ("Pão de Queijo Amostra 500g", "padaria", "pct", "16.50", "9.90", "48", False, True),
    ("Croissant de Teste", "padaria", "un", "7.20", "3.80", "36", False, False),
    ("Bolo de Cenoura Fictício", "padaria", "un", "28.00", "15.20", "14", False, False),
    ("Sonho Recheado Demo", "padaria", "un", "6.50", "3.10", "30", False, False),
    ("Baguete Exemplo", "padaria", "un", "8.40", "4.20", "25", False, False),
    # --- Hortifruti ----------------------------------------------------------
    ("Banana Prata Amostra", "hortifruti", "kg", "7.90", "4.30", "85.000", True, True),
    ("Tomate Italiano Demo", "hortifruti", "kg", "11.40", "6.80", "52.000", True, False),
    ("Alface Crespa Fictícia", "hortifruti", "un", "4.90", "2.40", "40", False, False),
    ("Maçã Gala de Teste", "hortifruti", "kg", "13.90", "8.10", "63.000", True, False),
    ("Batata Inglesa Amostra", "hortifruti", "kg", "6.40", "3.50", "120.000", True, False),
    ("Cebola Demo", "hortifruti", "kg", "5.80", "3.10", "95.000", True, False),
    ("Cenoura Fictícia", "hortifruti", "kg", "6.20", "3.40", "70.000", True, False),
    ("Abacate Exemplo", "hortifruti", "kg", "12.50", "7.20", "28.000", True, False),
    ("Limão Tahiti Demo", "hortifruti", "kg", "8.90", "4.60", "44.000", True, False),
    # --- Açougue -------------------------------------------------------------
    ("Peito de Frango Fictício", "acougue", "kg", "22.90", "16.40", "38.000", True, True),
    ("Coxão Mole Amostra", "acougue", "kg", "54.90", "41.00", "22.000", True, False),
    ("Linguiça Toscana Demo", "acougue", "kg", "26.50", "18.20", "30.000", True, False),
    ("Costela Bovina Exemplo", "acougue", "kg", "39.90", "29.50", "18.000", True, False),
    ("Bacon Fatiado Fictício", "acougue", "pct", "21.90", "14.80", "26", False, False),
    ("Filé de Tilápia Demo", "acougue", "kg", "44.90", "33.00", "15.000", True, False),
    # --- Laticínios ----------------------------------------------------------
    ("Leite Integral Demonstração 1L", "laticinios", "l", "6.20", "4.10", "140", False, True),
    ("Queijo Mussarela Fictício", "laticinios", "kg", "52.00", "38.00", "16.000", True, False),
    ("Iogurte Natural Amostra 170g", "laticinios", "un", "3.60", "1.90", "90", False, False),
    ("Manteiga Exemplo 200g", "laticinios", "un", "18.90", "13.20", "44", False, False),
    ("Requeijão Demo 200g", "laticinios", "un", "9.40", "5.80", "52", False, False),
    ("Queijo Prato Fictício", "laticinios", "kg", "48.50", "35.00", "12.000", True, False),
    # --- Mercearia -----------------------------------------------------------
    ("Arroz Fictício Tipo 1 5kg", "mercearia", "pct", "29.90", "22.40", "80", False, True),
    ("Feijão Carioca Amostra 1kg", "mercearia", "pct", "10.40", "7.20", "95", False, False),
    ("Macarrão Espaguete Demo 500g", "mercearia", "pct", "6.10", "3.60", "110", False, False),
    ("Açúcar Refinado Exemplo 1kg", "mercearia", "pct", "5.90", "3.80", "88", False, False),
    ("Café Torrado Fictício 500g", "mercearia", "pct", "24.90", "17.50", "64", False, True),
    ("Óleo de Soja Demo 900ml", "mercearia", "grf", "8.70", "6.10", "76", False, False),
    ("Sal Refinado Amostra 1kg", "mercearia", "pct", "3.40", "1.80", "70", False, False),
    ("Farinha de Trigo Fictícia 1kg", "mercearia", "pct", "7.20", "4.40", "58", False, False),
    ("Molho de Tomate Demo 340g", "mercearia", "un", "4.60", "2.50", "120", False, False),
    ("Milho Verde Exemplo 200g", "mercearia", "un", "4.90", "2.70", "84", False, False),
    # --- Bebidas -------------------------------------------------------------
    ("Água Mineral Fictícia 1,5L", "bebidas", "grf", "3.60", "1.70", "160", False, False),
    ("Refrigerante Amostra 2L", "bebidas", "grf", "10.90", "6.80", "92", False, True),
    ("Suco de Laranja Demo 1L", "bebidas", "l", "11.40", "7.20", "48", False, False),
    ("Cerveja Fictícia Lata 350ml", "bebidas", "un", "4.80", "3.10", "180", False, False),
    ("Chá Gelado Exemplo 1,5L", "bebidas", "grf", "8.90", "5.40", "56", False, False),
    ("Energético Demo 250ml", "bebidas", "un", "9.90", "6.30", "72", False, False),
    # --- Limpeza -------------------------------------------------------------
    ("Detergente Fictício 500ml", "limpeza", "un", "3.20", "1.60", "130", False, False),
    ("Sabão em Pó Amostra 1kg", "limpeza", "pct", "19.90", "13.40", "48", False, False),
    ("Água Sanitária Demo 1L", "limpeza", "l", "5.40", "2.90", "86", False, False),
    ("Amaciante Exemplo 2L", "limpeza", "grf", "16.90", "11.20", "40", False, False),
    # --- Higiene -------------------------------------------------------------
    ("Sabonete Fictício 90g", "higiene", "un", "3.10", "1.50", "150", False, False),
    ("Shampoo Amostra 350ml", "higiene", "un", "22.90", "15.10", "38", False, False),
    ("Papel Higiênico Demo 12un", "higiene", "pct", "27.90", "19.60", "44", False, True),
)

SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Padaria", "padaria", ("Pães", "Bolos e Doces", "Salgados")),
    ("Hortifruti", "hortifruti", ("Frutas", "Legumes", "Verduras")),
    ("Açougue", "acougue", ("Bovinos", "Aves", "Peixes")),
    ("Laticínios", "laticinios", ("Leites", "Queijos", "Iogurtes")),
    ("Mercearia", "mercearia", ("Grãos", "Massas", "Enlatados")),
    ("Bebidas", "bebidas", ("Águas", "Sucos", "Refrigerantes")),
    ("Limpeza", "limpeza", ("Roupas", "Casa")),
    ("Higiene", "higiene", ("Cuidado Pessoal",)),
)


class Command(BaseCommand):
    help = "Replace the catalog with 50 fictitious products across eight sections."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--tenant", default="", help="Tenant slug.")
        parser.add_argument(
            "--keep-existing",
            action="store_true",
            help="Add to the catalog instead of replacing it.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running with DEBUG=False.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to reseed the catalog with DEBUG=False. Pass --force if this "
                "really is a throwaway environment."
            )

        from apps.catalog.models import Brand, Category, Product, UnitOfMeasure
        from apps.tenants.models import Tenant

        tenant = self._resolve_tenant(Tenant, options["tenant"])

        if not options["keep_existing"]:
            self._purge(Product)

        units = {unit.code: unit for unit in UnitOfMeasure.objects.filter(tenant=tenant)}
        if not units:
            raise CommandError(
                "This tenant has no units of measure. Run `bootstrap_tenant` first "
                "(the `create_admin` command does it for you)."
            )

        categories = self._ensure_sections(Category, tenant)
        brand, _ = Brand.objects.get_or_create(
            tenant=tenant,
            slug="marca-exemplo",
            defaults={"name": "Marca Exemplo"},
        )

        created = self._create_products(tenant, categories, units, brand)

        self.stdout.write(self.style.SUCCESS(f"\nSeeded {created} products.\n"))
        self.stdout.write(f"  Tenant   : {tenant.trade_name} ({tenant.slug})")
        self.stdout.write(f"  Sections : {len(SECTIONS)}")
        self.stdout.write(f"  Total    : {Product.objects.filter(tenant=tenant).count()} products")
        self.stdout.write(
            self.style.WARNING("\n  All names and prices are fictitious demonstration data.\n")
        )

    # --- Steps ---------------------------------------------------------------
    def _resolve_tenant(self, tenant_model: Any, slug: str) -> Any:
        if slug:
            tenant = tenant_model.objects.filter(slug=slug).first()
            if tenant is None:
                raise CommandError(f"No tenant with slug '{slug}'.")
            return tenant

        tenants = list(tenant_model.objects.all()[:2])
        if not tenants:
            raise CommandError("No tenant exists. Run `create_admin` first.")
        if len(tenants) > 1:
            raise CommandError("Several tenants exist. Pass --tenant <slug>.")
        return tenants[0]

    def _purge(self, product_model: Any) -> None:
        """Remove every product and everything that hangs off one.

        Products referenced by an order are archived rather than deleted:
        deleting them would break order history and every report derived from
        it (invariant #3).
        """
        from apps.catalog.constants import ProductStatus
        from apps.orders.models import OrderItem

        sold_ids = set(
            OrderItem.objects.filter(product__isnull=False).values_list("product_id", flat=True)
        )

        archived = product_model.objects.filter(pk__in=sold_ids).update(
            status=ProductStatus.ARCHIVED, is_active=False
        )
        deleted, _ = product_model.objects.exclude(pk__in=sold_ids).delete()

        self.stdout.write(
            self.style.WARNING(
                f"Removed {deleted} product row(s); archived {archived} still referenced by orders."
            )
        )

    def _ensure_sections(self, category_model: Any, tenant: Any) -> dict[str, Any]:
        from apps.catalog.services import unique_slug

        categories: dict[str, Any] = {}
        for position, (name, slug, children) in enumerate(SECTIONS):
            parent, _ = category_model.objects.get_or_create(
                tenant=tenant,
                slug=slug,
                defaults={"name": name, "position": position, "is_featured": position < 5},
            )
            categories[slug] = parent

            for child_position, child_name in enumerate(children):
                child_slug = unique_slug(category_model, tenant.pk, f"{slug}-{child_name}")
                category_model.objects.get_or_create(
                    tenant=tenant,
                    parent=parent,
                    name=child_name,
                    defaults={"slug": child_slug, "position": child_position},
                )

        return categories

    def _create_products(
        self, tenant: Any, categories: dict[str, Any], units: dict[str, Any], brand: Any
    ) -> int:
        from apps.catalog.constants import ProductStatus, ProductType
        from apps.catalog.models import Product
        from apps.catalog.services import create_product
        from apps.inventory.services import set_stock
        from apps.pricing.services import set_price

        rng = random.Random(2026)  # noqa: S311 - deterministic demo data, not crypto
        created = 0

        for name, section, unit_code, price, cost, stock, weighted, featured in CATALOG:
            if Product.objects.filter(tenant=tenant, name=name).exists():
                continue

            product = create_product(
                tenant=tenant,
                name=name,
                category=categories[section],
                sale_unit=units.get(unit_code) or units["un"],
                brand=brand,
                short_description="Produto fictício para demonstração da plataforma.",
                description=(
                    "Este item existe apenas para demonstrar o catálogo do MurasFood. "
                    "Nome, preço e disponibilidade são fictícios e não correspondem a "
                    "nenhum produto real."
                ),
                product_type=ProductType.WEIGHTED if weighted else ProductType.SIMPLE,
                status=ProductStatus.ACTIVE,
                is_featured=featured,
                requires_weighing=weighted,
            )

            set_price(tenant=tenant, product=product, base_price=price, cost_price=cost)
            set_stock(product=product, quantity=stock, note="Estoque inicial de demonstração")

            self._seed_price_history(tenant, product, Decimal(price), Decimal(cost), rng)
            created += 1

        return created

    def _seed_price_history(
        self, tenant: Any, product: Any, price: Decimal, cost: Decimal, rng: random.Random
    ) -> None:
        """Backdate a few price changes so the product chart has a real series.

        Writes through the pricing service, so every point lands in
        ``PriceHistory`` exactly as a genuine change would.
        """
        from apps.pricing.models import PriceChangeReason, PriceHistory
        from apps.pricing.services import set_price

        current = price
        points = rng.randint(3, 6)

        for index in range(points):
            # Walk backwards from today in roughly fortnightly steps.
            days_ago = (points - index) * rng.randint(9, 18)
            drift = Decimal(str(rng.uniform(-0.09, 0.09))).quantize(Decimal("0.01"))
            previous = (current * (Decimal("1") + drift)).quantize(Decimal("0.01"))
            if previous <= Decimal("0.50"):
                continue

            set_price(
                tenant=tenant,
                product=product,
                base_price=previous,
                cost_price=cost,
                reason=PriceChangeReason.MANUAL,
                note="Histórico de demonstração",
            )

            # Backdate the entry the service just wrote.
            entry = (
                PriceHistory.objects.filter(product=product, field="base_price")
                .order_by("-created_at")
                .first()
            )
            if entry is not None:
                stamp = timezone.now() - timedelta(days=days_ago)
                PriceHistory.objects.filter(pk=entry.pk).update(created_at=stamp)

        # Finish on the catalogue price so the storefront shows the intended value.
        set_price(tenant=tenant, product=product, base_price=price, cost_price=cost)

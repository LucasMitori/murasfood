"""
Development seed data.

Everything created here is **obviously fake** (spec §72). No real merchant name,
address, product or price appears in this file, and the command refuses to run
with ``DEBUG=False`` unless explicitly forced — seed data in production is how
demo accounts end up taking real orders.
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

DEMO_PASSWORD = "demo1234"

DEMO_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Padaria", "padaria", ("Pães", "Bolos", "Salgados")),
    ("Hortifruti", "hortifruti", ("Frutas", "Legumes", "Verduras")),
    ("Mercearia", "mercearia", ("Grãos", "Massas", "Enlatados")),
    ("Bebidas", "bebidas", ("Águas", "Sucos", "Refrigerantes")),
    ("Laticínios", "laticinios", ("Leites", "Queijos", "Iogurtes")),
    ("Limpeza", "limpeza", ("Roupas", "Casa")),
)

# (name, category slug, unit code, base price, cost, stock, weighted?)
DEMO_PRODUCTS: tuple[tuple[str, str, str, str, str, str, bool], ...] = (
    ("Pão de Forma Demonstração 500g", "padaria", "un", "8.90", "5.10", "40", False),
    ("Pão Francês Fictício", "padaria", "kg", "16.50", "9.80", "25.500", True),
    ("Bolo de Teste Fatiado", "padaria", "un", "24.00", "13.20", "12", False),
    ("Coxinha Exemplo", "padaria", "un", "7.50", "3.90", "60", False),
    ("Banana Amostra", "hortifruti", "kg", "6.90", "3.80", "80.000", True),
    ("Tomate Demonstração", "hortifruti", "kg", "9.40", "5.20", "45.000", True),
    ("Alface Fictícia", "hortifruti", "un", "4.20", "2.10", "30", False),
    ("Maçã de Teste", "hortifruti", "kg", "11.90", "7.10", "55.000", True),
    ("Arroz Fictício 5kg", "mercearia", "pct", "27.90", "20.40", "60", False),
    ("Feijão Exemplo 1kg", "mercearia", "pct", "9.80", "6.90", "70", False),
    ("Macarrão Amostra 500g", "mercearia", "pct", "5.60", "3.20", "90", False),
    ("Milho Enlatado Demo", "mercearia", "un", "4.90", "2.80", "50", False),
    ("Água Mineral Fictícia 1,5L", "bebidas", "grf", "3.20", "1.60", "120", False),
    ("Suco de Teste 1L", "bebidas", "l", "8.40", "4.90", "40", False),
    ("Refrigerante Amostra 2L", "bebidas", "grf", "9.90", "6.10", "65", False),
    ("Leite Demonstração 1L", "laticinios", "l", "5.80", "3.90", "100", False),
    ("Queijo Fictício Fatiado", "laticinios", "kg", "48.00", "31.00", "12.000", True),
    ("Iogurte Exemplo 170g", "laticinios", "un", "3.40", "1.90", "80", False),
    ("Detergente de Teste 500ml", "limpeza", "un", "3.10", "1.70", "70", False),
    ("Sabão em Pó Amostra 1kg", "limpeza", "pct", "18.90", "12.40", "35", False),
)


class Command(BaseCommand):
    help = "Create an obviously fake demo tenant with catalog, orders and finance data."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--slug", default="demo", help="Tenant slug (default: demo)")
        parser.add_argument("--orders", type=int, default=25, help="Number of sample orders")
        parser.add_argument("--reset", action="store_true", help="Delete the tenant first")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding with DEBUG=False. Do not use in production.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed with DEBUG=False. Pass --force if this really is a "
                "throwaway environment."
            )

        # Seeding queues a lot of transactional email. Capture it in memory so
        # the command does not depend on a reachable SMTP server.
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        slug: str = options["slug"]
        if options["reset"]:
            self._reset(slug)

        tenant = self._create_tenant(slug)
        users = self._create_users(tenant)
        units = self._catalog(tenant)
        self._promotions(tenant)
        self._orders(tenant, users["customer"], count=options["orders"])
        self._expenses(tenant)

        self.stdout.write(self.style.SUCCESS("\nDemo data ready.\n"))
        self.stdout.write(f"  Tenant     : {tenant.trade_name} ({tenant.slug})")
        self.stdout.write(f"  Admin      : admin@demo.test / {DEMO_PASSWORD}")
        self.stdout.write(f"  Manager    : gerente@demo.test / {DEMO_PASSWORD}")
        self.stdout.write(f"  Customer   : cliente@demo.test / {DEMO_PASSWORD}")
        self.stdout.write(f"  Units      : {', '.join(sorted(units))}")
        self.stdout.write("\n  All data is fictitious. Never seed a production database.\n")

    # --- Steps ---------------------------------------------------------------
    def _reset(self, slug: str) -> None:
        from apps.tenants.models import Tenant

        deleted, _ = Tenant.objects.filter(slug=slug).delete()
        if deleted:
            self.stdout.write(self.style.WARNING(f"Removed existing tenant '{slug}'."))

    @transaction.atomic
    def _create_tenant(self, slug: str) -> Any:
        from apps.tenants.bootstrap import bootstrap_tenant
        from apps.tenants.models import BusinessHours, Tenant
        from apps.tenants.services import create_tenant

        existing = Tenant.objects.filter(slug=slug).first()
        if existing is not None:
            bootstrap_tenant(existing)
            self.stdout.write(f"Using existing tenant '{slug}'.")
            return existing

        tenant = create_tenant(
            legal_name="Mercado Demonstração LTDA",
            trade_name="Mercado Demonstração",
            support_email="contato@demo.test",
            slug=slug,
            phone="+55 11 90000-0000",
            postal_code="01001000",
            street="Rua Fictícia de Exemplo",
            number="100",
            neighborhood="Bairro Amostra",
            city="Cidade Exemplo",
            state="SP",
            tax_id="00.000.000/0001-00",
        )
        bootstrap_tenant(tenant)

        for weekday in range(1, 7):
            BusinessHours.objects.get_or_create(
                tenant=tenant,
                weekday=weekday,
                opens_at="08:00",
                defaults={"closes_at": "20:00"},
            )
        BusinessHours.objects.get_or_create(
            tenant=tenant, weekday=7, opens_at="08:00", defaults={"closes_at": "13:00"}
        )

        from apps.delivery.selectors import get_settings

        delivery = get_settings(tenant)
        delivery.base_fee = Decimal("7.90")
        delivery.free_delivery_threshold = Decimal("120.00")
        delivery.minimum_order_amount = Decimal("20.00")
        delivery.save()

        self.stdout.write(self.style.SUCCESS(f"Created tenant '{slug}'."))
        return tenant

    def _create_users(self, tenant: Any) -> dict[str, Any]:
        from apps.accounts.constants import SystemRole, UserType
        from apps.accounts.models import Address, Role, User
        from apps.accounts.services import assign_role

        def make(email: str, user_type: str, first: str, last: str) -> User:
            user = User.objects.filter(tenant=tenant, email=email).first()
            if user is not None:
                return user
            return User.objects.create_user(
                email=email,
                password=DEMO_PASSWORD,
                tenant=tenant,
                first_name=first,
                last_name=last,
                user_type=user_type,
                is_verified=True,
            )

        admin = make("admin@demo.test", UserType.ADMINISTRATOR, "Ana", "Administradora")
        manager = make("gerente@demo.test", UserType.MANAGER, "Gabriel", "Gerente")
        staff = make("atendente@demo.test", UserType.STAFF, "Sofia", "Atendente")
        customer = make("cliente@demo.test", UserType.CUSTOMER, "Carlos", "Cliente")

        roles = {role.slug: role for role in Role.objects.filter(tenant=tenant)}
        for user, slug in (
            (admin, SystemRole.ADMINISTRATOR),
            (manager, SystemRole.MANAGER),
            (staff, SystemRole.STAFF),
        ):
            if slug in roles:
                assign_role(user, roles[slug], granted_by=admin)

        Address.objects.get_or_create(
            tenant=tenant,
            customer=customer,
            label="Casa",
            defaults={
                "recipient_name": "Carlos Cliente",
                "postal_code": "01002000",
                "street": "Rua de Amostra",
                "number": "42",
                "neighborhood": "Bairro Fictício",
                "city": "Cidade Exemplo",
                "state": "SP",
                "is_default": True,
            },
        )

        self.stdout.write("Created demo users.")
        return {"admin": admin, "manager": manager, "staff": staff, "customer": customer}

    def _catalog(self, tenant: Any) -> dict[str, Any]:
        from apps.catalog.constants import ProductStatus, ProductType
        from apps.catalog.models import Brand, Category, UnitOfMeasure
        from apps.catalog.services import create_product, unique_slug
        from apps.inventory.services import set_stock
        from apps.pricing.services import set_price

        units = {unit.code: unit for unit in UnitOfMeasure.objects.filter(tenant=tenant)}

        brand, _ = Brand.objects.get_or_create(
            tenant=tenant, slug="marca-exemplo", defaults={"name": "Marca Exemplo"}
        )

        categories: dict[str, Category] = {}
        for position, (name, slug, children) in enumerate(DEMO_CATEGORIES):
            parent, _ = Category.objects.get_or_create(
                tenant=tenant,
                slug=slug,
                defaults={"name": name, "position": position, "is_featured": position < 4},
            )
            categories[slug] = parent
            for child_position, child_name in enumerate(children):
                Category.objects.get_or_create(
                    tenant=tenant,
                    slug=unique_slug(Category, tenant.pk, f"{slug}-{child_name}"),
                    defaults={"name": child_name, "parent": parent, "position": child_position},
                )

        created = 0
        for name, category_slug, unit_code, price, cost, stock, weighted in DEMO_PRODUCTS:
            from apps.catalog.models import Product

            if Product.objects.filter(tenant=tenant, name=name).exists():
                continue

            product = create_product(
                tenant=tenant,
                name=name,
                category=categories[category_slug],
                sale_unit=units.get(unit_code) or units["un"],
                brand=brand,
                short_description="Produto fictício para demonstração.",
                description=(
                    "Este item existe apenas para demonstrar o catálogo do MurasFood. "
                    "Nenhuma informação aqui corresponde a um produto real."
                ),
                product_type=ProductType.WEIGHTED if weighted else ProductType.SIMPLE,
                status=ProductStatus.ACTIVE,
                is_featured=created % 5 == 0,
                requires_weighing=weighted,
            )
            set_price(tenant=tenant, product=product, base_price=price, cost_price=cost)
            set_stock(product=product, quantity=stock, note="Estoque inicial de demonstração")
            created += 1

        self.stdout.write(f"Created {created} demo products.")
        return units

    def _promotions(self, tenant: Any) -> None:
        from apps.promotions.models import Coupon, DiscountType, Promotion, PromotionScope

        promotion, created = Promotion.objects.get_or_create(
            tenant=tenant,
            name="Cupom de boas-vindas (demo)",
            defaults={
                "description": "10% de desconto para novos clientes — apenas demonstração.",
                "discount_type": DiscountType.PERCENTAGE,
                "scope": PromotionScope.ORDER,
                "value": Decimal("10.00"),
                "max_discount_amount": Decimal("25.00"),
                "minimum_order_amount": Decimal("40.00"),
                "requires_coupon": True,
                "is_active": True,
            },
        )
        if created:
            Coupon.objects.get_or_create(
                tenant=tenant,
                code="BEMVINDO10",
                defaults={"promotion": promotion, "max_uses_per_customer": 1},
            )

        Promotion.objects.get_or_create(
            tenant=tenant,
            name="Frete grátis acima de R$150 (demo)",
            defaults={
                "discount_type": DiscountType.FREE_DELIVERY,
                "scope": PromotionScope.ORDER,
                "minimum_order_amount": Decimal("150.00"),
                "is_stackable": True,
                "is_active": True,
            },
        )
        self.stdout.write("Created demo promotions.")

    def _orders(self, tenant: Any, customer: Any, *, count: int) -> None:
        """Create sample orders spread over the last 60 days.

        Statuses are moved through the real state machine, so the demo data
        exercises the same transitions production does.
        """
        from apps.accounts.models import Address
        from apps.cart.models import Cart
        from apps.cart.services import add_item
        from apps.catalog.models import Product
        from apps.orders.constants import OrderStatus
        from apps.orders.models import Order
        from apps.orders.services import create_order_from_cart, transition_order
        from apps.payments.constants import PaymentStatus
        from apps.payments.services import apply_payment_status, create_payment_for_order

        if Order.objects.filter(tenant=tenant).count() >= count:
            self.stdout.write("Demo orders already present.")
            return

        products = list(Product.objects.filter(tenant=tenant, status="ACTIVE")[:20])
        if not products:
            return

        address = Address.objects.filter(customer=customer).first()
        rng = random.Random(42)
        created = 0

        for index in range(count):
            cart = Cart.objects.create(tenant=tenant, customer=customer)
            for product in rng.sample(products, rng.randint(2, 5)):
                quantity = (
                    Decimal(str(round(rng.uniform(0.3, 2.0), 3)))
                    if product.sells_fractional_quantity
                    else Decimal(rng.randint(1, 3))
                )
                try:
                    add_item(cart=cart, product=product, quantity=quantity)
                except Exception:
                    continue

            if cart.is_empty:
                cart.delete()
                continue

            delivery_method = "DELIVERY" if index % 3 else "PICKUP"
            try:
                order = create_order_from_cart(
                    tenant=tenant,
                    cart=cart,
                    delivery_method=delivery_method,
                    address=address if delivery_method == "DELIVERY" else None,
                    customer=customer,
                    customer_note="Pedido de demonstração.",
                )
            except Exception:
                # Stock exhaustion is expected while generating demo orders.
                # A failed checkout leaves the cart ACTIVE, and a customer may
                # hold only one active cart per tenant. Drop it, or the next
                # iteration trips the unique constraint.
                cart.delete()
                continue

            # Backdate so the dashboard has a meaningful history.
            placed = timezone.now() - timedelta(days=rng.randint(0, 59), hours=rng.randint(0, 12))
            Order.objects.filter(pk=order.pk).update(created_at=placed, placed_at=placed)
            order.refresh_from_db()

            payment = create_payment_for_order(order=order)

            outcome = rng.random()
            if outcome < 0.1:
                transition_order(order, to_status=OrderStatus.CANCELLED, reason="Demonstração")
            else:
                apply_payment_status(payment, status=PaymentStatus.PAID, paid_at=placed)
                order.refresh_from_db()
                Order.objects.filter(pk=order.pk).update(paid_at=placed)

                if outcome < 0.85:
                    for target in (
                        OrderStatus.PREPARING,
                        OrderStatus.OUT_FOR_DELIVERY
                        if delivery_method == "DELIVERY"
                        else OrderStatus.READY_FOR_PICKUP,
                        OrderStatus.DELIVERED
                        if delivery_method == "DELIVERY"
                        else OrderStatus.COMPLETED,
                    ):
                        order.refresh_from_db()
                        try:
                            transition_order(order, to_status=target, reason="Demonstração")
                        except Exception:
                            break
            created += 1

        self.stdout.write(f"Created {created} demo orders.")

        from apps.reports.tasks import project_paid_orders_to_ledger

        project_paid_orders_to_ledger()

    def _expenses(self, tenant: Any) -> None:
        from apps.finance.services import record_expense

        today = timezone.now().date()
        samples = (
            ("rent", "3200.00", "Aluguel (demonstração)"),
            ("payroll", "8400.00", "Folha de pagamento (demonstração)"),
            ("utilities", "760.00", "Energia e água (demonstração)"),
            ("marketing", "450.00", "Panfletos (demonstração)"),
        )
        for months_ago in range(3):
            # Walk back whole months by stepping off the first of the month.
            reference = today.replace(day=1)
            for _ in range(months_ago):
                reference = (reference - timedelta(days=1)).replace(day=1)
            reference = reference.replace(day=5)

            for code, amount, description in samples:
                record_expense(
                    tenant=tenant,
                    category_code=code,
                    amount=Decimal(amount),
                    occurred_on=reference,
                    description=description,
                )
        self.stdout.write("Created demo expenses.")

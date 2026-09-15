"""
The help page, editable.

These answers used to be locale strings, so a shop could not correct its own
delivery window without a deploy and every shop on the platform answered
identically. The tests are mostly about the one thing that makes draft/published
worth having over a visibility flag: an unfinished answer must be invisible to
customers while still being there for the person writing it.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.tenants.models import FaqCategory, FaqEntry, FaqStatus

pytestmark = pytest.mark.django_db

ADMIN_CATEGORIES = "/api/v1/tenants/admin/faq-categories/"
ADMIN_ENTRIES = "/api/v1/tenants/admin/faq/"
PUBLIC = "/api/v1/tenants/faq/"


@pytest.fixture
def section(tenant: Any) -> FaqCategory:
    return FaqCategory.objects.create(
        tenant=tenant, name="Pedidos", slug="pedidos", icon="mdi-receipt-text-outline"
    )


def make_entry(tenant: Any, section: FaqCategory, **overrides: Any) -> FaqEntry:
    return FaqEntry.objects.create(
        tenant=tenant,
        category=section,
        question=overrides.pop("question", "Como acompanho meu pedido?"),
        answer=overrides.pop("answer", "Em Meus pedidos."),
        **overrides,
    )


class TestDraftsAreInvisible:
    def test_a_draft_never_reaches_a_visitor(
        self, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        """The whole reason this is two states rather than one flag."""
        make_entry(tenant, section, status=FaqStatus.DRAFT)

        assert api_client.get(PUBLIC).json() == []

    def test_publishing_makes_it_visible(
        self, admin_client_api: Any, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        entry = make_entry(tenant, section)

        response = admin_client_api.post(f"{ADMIN_ENTRIES}{entry.pk}/publish/")

        assert response.status_code == 200
        assert response.json()["status"] == FaqStatus.PUBLISHED
        assert response.json()["published_at"] is not None

        body = api_client.get(PUBLIC).json()
        assert body[0]["entries"][0]["question"] == entry.question

    def test_unpublishing_hides_it_without_losing_the_copy(
        self, admin_client_api: Any, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        """Hiding is not deleting: the merchant gets their wording back."""
        entry = make_entry(tenant, section, status=FaqStatus.PUBLISHED)

        admin_client_api.post(f"{ADMIN_ENTRIES}{entry.pk}/unpublish/")

        assert api_client.get(PUBLIC).json() == []
        entry.refresh_from_db()
        assert entry.answer == "Em Meus pedidos."

    def test_a_section_with_nothing_published_is_not_rendered(
        self, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        """An empty heading is noise on a help page."""
        make_entry(tenant, section, status=FaqStatus.DRAFT)

        assert api_client.get(PUBLIC).json() == []

    def test_an_inactive_section_is_hidden_with_its_entries(
        self, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        make_entry(tenant, section, status=FaqStatus.PUBLISHED)
        FaqCategory.objects.filter(pk=section.pk).update(is_active=False)

        assert api_client.get(PUBLIC).json() == []


class TestOrdering:
    def test_entries_come_back_in_their_stored_order(
        self, api_client: Any, tenant: Any, section: FaqCategory
    ) -> None:
        make_entry(tenant, section, question="Segunda", position=1, status=FaqStatus.PUBLISHED)
        make_entry(tenant, section, question="Primeira", position=0, status=FaqStatus.PUBLISHED)

        entries = api_client.get(PUBLIC).json()[0]["entries"]

        assert [entry["question"] for entry in entries] == ["Primeira", "Segunda"]

    def test_reorder_writes_the_whole_list(
        self, admin_client_api: Any, tenant: Any, section: FaqCategory
    ) -> None:
        first = make_entry(tenant, section, question="A", position=0)
        second = make_entry(tenant, section, question="B", position=1)

        response = admin_client_api.post(
            f"{ADMIN_ENTRIES}reorder/",
            {"order": [str(second.pk), str(first.pk)]},
            format="json",
        )

        assert response.status_code == 200
        first.refresh_from_db()
        second.refresh_from_db()
        assert (second.position, first.position) == (0, 1)


class TestTenantIsolation:
    def test_a_shop_only_sees_its_own_questions(
        self, api_client: Any, tenant: Any, other_tenant: Any, section: FaqCategory
    ) -> None:
        make_entry(tenant, section, status=FaqStatus.PUBLISHED)

        other_section = FaqCategory.objects.create(
            tenant=other_tenant, name="Outra", slug="outra"
        )
        FaqEntry.objects.create(
            tenant=other_tenant,
            category=other_section,
            question="Do outro mercado",
            answer="x",
            status=FaqStatus.PUBLISHED,
        )

        body = api_client.get(PUBLIC).json()

        questions = [entry["question"] for group in body for entry in group["entries"]]
        assert "Do outro mercado" not in questions

    def test_an_entry_cannot_be_filed_under_another_shops_section(
        self, admin_client_api: Any, other_tenant: Any
    ) -> None:
        """`category` is a plain primary-key field: without the check it accepts
        any id in the table, which is a cross-tenant write."""
        foreign = FaqCategory.objects.create(tenant=other_tenant, name="Deles", slug="deles")

        response = admin_client_api.post(
            ADMIN_ENTRIES,
            {"category": str(foreign.pk), "question": "Q", "answer": "A"},
            format="json",
        )

        assert response.status_code == 400


class TestAccess:
    def test_a_visitor_cannot_write(
        self, api_client: Any, section: FaqCategory
    ) -> None:
        response = api_client.post(
            ADMIN_ENTRIES,
            {"category": str(section.pk), "question": "Q", "answer": "A"},
            format="json",
        )

        assert response.status_code in {401, 403}

    def test_a_customer_cannot_write(self, customer_client: Any, section: FaqCategory) -> None:
        response = customer_client.post(
            ADMIN_ENTRIES,
            {"category": str(section.pk), "question": "Q", "answer": "A"},
            format="json",
        )

        assert response.status_code == 403

    def test_the_public_page_needs_no_account(self, api_client: Any) -> None:
        assert api_client.get(PUBLIC).status_code == 200


class TestCategories:
    def test_creating_one_derives_a_slug(self, admin_client_api: Any) -> None:
        response = admin_client_api.post(
            ADMIN_CATEGORIES, {"name": "Entrega e Frete"}, format="json"
        )

        assert response.status_code == 201
        assert response.json()["slug"] == "entrega-e-frete"

    def test_deleting_a_section_takes_its_questions(
        self, admin_client_api: Any, tenant: Any, section: FaqCategory
    ) -> None:
        make_entry(tenant, section)

        admin_client_api.delete(f"{ADMIN_CATEGORIES}{section.pk}/")

        assert not FaqEntry.objects.filter(category_id=section.pk).exists()

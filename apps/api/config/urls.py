"""
Root URL configuration.

Every business endpoint lives under ``/api/v1/`` so that a future ``v2`` can be
introduced without breaking existing mobile clients. Health endpoints are
deliberately unversioned: orchestrators must not care about API versions.
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.views import LivenessView, ReadinessView

api_v1_patterns = [
    path("auth/", include("apps.accounts.urls.auth")),
    path("customers/", include("apps.accounts.urls.customers")),
    path("tenants/", include("apps.tenants.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("cart/", include("apps.cart.urls")),
    path("shopping-lists/", include("apps.cart.shopping_list_urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("delivery/", include("apps.delivery.urls")),
    path("media/", include("apps.media.urls")),
    path("promotions/", include("apps.promotions.urls")),
    path("admin/", include("apps.accounts.urls.admin")),
    path("admin/", include("apps.catalog.admin_urls")),
    path("admin/", include("apps.orders.admin_urls")),
    path("admin/", include("apps.reports.urls")),
    path("admin/", include("apps.finance.urls")),
    path("admin/", include("apps.audit.urls")),
    path("admin/", include("apps.inventory.urls")),
    path("admin/", include("apps.pricing.urls")),
    path("admin/", include("apps.notifications.urls")),
]

urlpatterns = [
    # Health probes for Docker/Kubernetes and the deployment pipeline.
    path("health/live/", LivenessView.as_view(), name="health-live"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
    # Emergency back-office. The real merchant dashboard is the Nuxt app.
    path("django-admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"))),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

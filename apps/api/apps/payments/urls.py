from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    OrderPaymentView,
    PaymentAdminViewSet,
    PaymentDetailView,
    PaymentEventViewSet,
    PaymentRefundViewSet,
    PaymentWebhookByProviderView,
    PaymentWebhookView,
    SandboxWebhookSimulatorView,
)

app_name = "payments"

router = DefaultRouter()
router.register("admin/payments", PaymentAdminViewSet, basename="admin-payment")
router.register("admin/payment-events", PaymentEventViewSet, basename="admin-payment-event")
router.register("admin/refunds", PaymentRefundViewSet, basename="admin-refund")

urlpatterns = [
    # Provider callbacks. Unauthenticated by necessity, signature-verified.
    path("webhooks/", PaymentWebhookView.as_view(), name="webhook"),
    path(
        "webhooks/<str:provider>/",
        PaymentWebhookByProviderView.as_view(),
        name="webhook-provider",
    ),
    path("", OrderPaymentView.as_view(), name="create"),
    path("<uuid:pk>/", PaymentDetailView.as_view(), name="detail"),
    path(
        "<uuid:pk>/simulate/",
        SandboxWebhookSimulatorView.as_view(),
        name="sandbox-simulate",
    ),
    path("", include(router.urls)),
]

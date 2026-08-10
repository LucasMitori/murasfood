"""Merchant order routes, mounted under ``/api/v1/admin/``."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminOrderViewSet

app_name = "orders-admin"

router = DefaultRouter()
router.register("orders", AdminOrderViewSet, basename="admin-order")

urlpatterns = [path("", include(router.urls))]

"""Merchant-facing catalog routes, mounted under ``/api/v1/admin/``."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminBrandViewSet,
    AdminCategoryViewSet,
    AdminProductViewSet,
    AdminTagViewSet,
    UnitOfMeasureViewSet,
)

app_name = "catalog-admin"

router = DefaultRouter()
router.register("products", AdminProductViewSet, basename="admin-product")
router.register("categories", AdminCategoryViewSet, basename="admin-category")
router.register("brands", AdminBrandViewSet, basename="admin-brand")
router.register("tags", AdminTagViewSet, basename="admin-tag")
router.register("units", UnitOfMeasureViewSet, basename="admin-unit")

urlpatterns = [path("", include(router.urls))]

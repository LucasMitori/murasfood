from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminFaqCategoryViewSet,
    AdminFaqEntryViewSet,
    BusinessHoursView,
    CurrentTenantView,
    PublicFaqView,
    TenantAdminView,
    TenantBrandingView,
    TenantSettingsView,
)

app_name = "tenants"

router = DefaultRouter()
router.register("admin/faq-categories", AdminFaqCategoryViewSet, basename="faq-category")
router.register("admin/faq", AdminFaqEntryViewSet, basename="faq-entry")

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
    path("faq/", PublicFaqView.as_view(), name="faq"),
    path("admin/", TenantAdminView.as_view(), name="admin"),
    path("admin/branding/", TenantBrandingView.as_view(), name="branding"),
    path("admin/settings/", TenantSettingsView.as_view(), name="settings"),
    path("admin/business-hours/", BusinessHoursView.as_view(), name="business-hours"),
    path("", include(router.urls)),
]

from django.urls import path

from .views import (
    BusinessHoursView,
    CurrentTenantView,
    TenantAdminView,
    TenantBrandingView,
    TenantSettingsView,
)

app_name = "tenants"

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
    path("admin/", TenantAdminView.as_view(), name="admin"),
    path("admin/branding/", TenantBrandingView.as_view(), name="branding"),
    path("admin/settings/", TenantSettingsView.as_view(), name="settings"),
    path("admin/business-hours/", BusinessHoursView.as_view(), name="business-hours"),
]

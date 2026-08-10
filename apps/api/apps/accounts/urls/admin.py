from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ..views import CustomerAdminViewSet, RoleViewSet, StaffUserViewSet

app_name = "accounts-admin"

router = DefaultRouter()
router.register("customers", CustomerAdminViewSet, basename="admin-customer")
router.register("users", StaffUserViewSet, basename="admin-user")
router.register("roles", RoleViewSet, basename="admin-role")

urlpatterns = [path("", include(router.urls))]

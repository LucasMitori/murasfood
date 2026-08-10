from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ..views import (
    CustomerAdminViewSet,
    PermissionListView,
    RoleViewSet,
    StaffUserViewSet,
    UserPermissionsView,
    UserRolesView,
)

app_name = "accounts-admin"

router = DefaultRouter()
router.register("customers", CustomerAdminViewSet, basename="admin-customer")
router.register("users", StaffUserViewSet, basename="admin-user")
router.register("roles", RoleViewSet, basename="admin-role")

urlpatterns = [
    path("permissions/", PermissionListView.as_view(), name="permissions"),
    path("users/<uuid:pk>/permissions/", UserPermissionsView.as_view(), name="user-permissions"),
    path("users/<uuid:pk>/roles/", UserRolesView.as_view(), name="user-roles"),
    path("", include(router.urls)),
]

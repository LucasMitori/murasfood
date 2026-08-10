from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.views import FavoriteViewSet

from ..views import AddressViewSet, ChangePasswordView, DataExportView, MeView

app_name = "customers"

router = DefaultRouter()
router.register("me/addresses", AddressViewSet, basename="address")
router.register("me/favorites", FavoriteViewSet, basename="favorite")

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("me/data-export/", DataExportView.as_view(), name="data-export"),
    path("", include(router.urls)),
]

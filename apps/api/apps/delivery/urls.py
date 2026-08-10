from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DeliveryConfigView,
    DeliveryOptionsView,
    DeliverySettingsView,
    DeliveryZoneViewSet,
)

app_name = "delivery"

router = DefaultRouter()
router.register("zones", DeliveryZoneViewSet, basename="zone")

urlpatterns = [
    path("config/", DeliveryConfigView.as_view(), name="config"),
    path("options/", DeliveryOptionsView.as_view(), name="options"),
    path("settings/", DeliverySettingsView.as_view(), name="settings"),
    path("", include(router.urls)),
]

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BannerEventView,
    BannerViewSet,
    DocumentViewSet,
    MediaAssetViewSet,
    MediaUploadView,
    PublicBannerListView,
)

app_name = "media"

router = DefaultRouter()
router.register("assets", MediaAssetViewSet, basename="asset")
router.register("documents", DocumentViewSet, basename="document")
router.register("banners", BannerViewSet, basename="banner")

urlpatterns = [
    path("upload/", MediaUploadView.as_view(), name="upload"),
    path("banners/live/", PublicBannerListView.as_view(), name="banners-live"),
    path("banners/<uuid:pk>/events/<str:event>/", BannerEventView.as_view(), name="banner-event"),
    path("", include(router.urls)),
]

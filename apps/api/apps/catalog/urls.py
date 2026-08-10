"""Public storefront catalog routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BarcodeLookupView,
    BrandViewSet,
    CategoryViewSet,
    ProductViewSet,
    SearchSuggestionView,
    StorefrontHomeView,
)

app_name = "catalog"

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")

urlpatterns = [
    path("home/", StorefrontHomeView.as_view(), name="home"),
    path("search/suggestions/", SearchSuggestionView.as_view(), name="search-suggestions"),
    path("barcode/<str:code>/", BarcodeLookupView.as_view(), name="barcode"),
    path("", include(router.urls)),
]

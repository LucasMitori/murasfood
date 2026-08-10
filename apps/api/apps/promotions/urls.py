from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CouponRedemptionViewSet,
    CouponValidateView,
    CouponViewSet,
    PromotionViewSet,
    PublicPromotionListView,
)

app_name = "promotions"

router = DefaultRouter()
router.register("promotions", PromotionViewSet, basename="promotion")
router.register("coupons", CouponViewSet, basename="coupon")
router.register("redemptions", CouponRedemptionViewSet, basename="redemption")

urlpatterns = [
    path("active/", PublicPromotionListView.as_view(), name="active"),
    path("coupons/validate/", CouponValidateView.as_view(), name="validate-coupon"),
    path("", include(router.urls)),
]

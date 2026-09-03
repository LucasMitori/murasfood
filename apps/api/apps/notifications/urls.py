from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EmailLogViewSet,
    EmailTemplatePreviewView,
    EmailTemplateTestView,
    EmailTemplateViewSet,
    NotificationViewSet,
)

app_name = "notifications"

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("email-templates", EmailTemplateViewSet, basename="email-template")
router.register("email-logs", EmailLogViewSet, basename="email-log")

urlpatterns = [
    path(
        "email-templates/<uuid:pk>/preview/",
        EmailTemplatePreviewView.as_view(),
        name="email-template-preview",
    ),
    path(
        "email-templates/<uuid:pk>/test/",
        EmailTemplateTestView.as_view(),
        name="email-template-test",
    ),
    path("", include(router.urls)),
]

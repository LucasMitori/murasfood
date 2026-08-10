from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EmailLogViewSet, EmailTemplateViewSet, NotificationViewSet

app_name = "notifications"

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("email-templates", EmailTemplateViewSet, basename="email-template")
router.register("email-logs", EmailLogViewSet, basename="email-log")

urlpatterns = [path("", include(router.urls))]

from rest_framework.routers import DefaultRouter

from .views import SystemAuditLogViewSet, SystemDeliveryViewSet, SystemWebhookViewSet

router = DefaultRouter()
router.register('webhooks', SystemWebhookViewSet, basename='system-webhooks')
router.register('deliveries', SystemDeliveryViewSet, basename='system-deliveries')
router.register('audit', SystemAuditLogViewSet, basename='system-audit')

superadmin_urlpatterns = router.urls

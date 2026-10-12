from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import N8nDeliveryCallbackView, NotificationViewSet, WhatsAppLogViewSet

router = DefaultRouter()
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('whatsapp-logs', WhatsAppLogViewSet, basename='whatsapp-logs')

admin_urlpatterns = router.urls

# Callback de n8n (secreto compartido, sin JWT)
n8n_urlpatterns = [
    path('deliveries/<int:delivery_id>/status/', N8nDeliveryCallbackView.as_view(), name='n8n-delivery-status'),
]

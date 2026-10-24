from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminPaymentViewSet,
    InitiatePaymentView, MercadoPagoWebhookView, PaymentStatusView,
    payment_success, payment_failure, payment_pending,
)

# URL patterns para las páginas HTML (template views)
template_urlpatterns = [
    path('payment/success/', payment_success, name='payment-success'),
    path('payment/failure/', payment_failure, name='payment-failure'),
    path('payment/pending/', payment_pending, name='payment-pending'),
]

public_urlpatterns = [
    path('payments/orders/<int:order_id>/initiate/', InitiatePaymentView.as_view(), name='payment-initiate'),
    path('payments/orders/<int:order_id>/status/', PaymentStatusView.as_view(), name='payment-status'),
    path('webhooks/mp/', MercadoPagoWebhookView.as_view(), name='webhook-mp'),
    # URL anterior (con slug del negocio): la tienen guardada en Mercado Pago las preferencias
    # creadas antes del cambio. Se puede quitar cuando ya no lleguen notificaciones a esta ruta.
    path('<slug:tenant_slug>/webhooks/mp/', MercadoPagoWebhookView.as_view(), name='webhook-mp-legacy'),
]

router = DefaultRouter()
router.register('payments', AdminPaymentViewSet, basename='admin-payments')

admin_urlpatterns = router.urls

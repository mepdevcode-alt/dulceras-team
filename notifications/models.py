from django.conf import settings
from django.db import models
from core.models import TenantModel


class Notification(TenantModel):
    NEW_ORDER = 'new_order'
    PAYMENT_RECEIVED = 'payment_received'
    ORDER_STATUS = 'order_status'

    TYPE_CHOICES = [
        (NEW_ORDER, 'Nuevo pedido'),
        (PAYMENT_RECEIVED, 'Pago recibido'),
        (ORDER_STATUS, 'Cambio de estado'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    order = models.ForeignKey(
        'orders.Order', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f"{self.get_type_display()} — {self.recipient}"


class WhatsAppLog(TenantModel):
    phone = models.CharField(max_length=50)
    message = models.TextField()
    order = models.ForeignKey(
        'orders.Order', null=True, blank=True, on_delete=models.SET_NULL
    )
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Log WhatsApp'
        verbose_name_plural = 'Logs WhatsApp'

    def __str__(self):
        return f"WA {self.phone} — {'OK' if self.sent else 'FALLIDO'}"


class MessageDelivery(TenantModel):
    """Registro de cada mensaje enviado al cliente de un pedido (vía n8n o Django)."""

    ORDER_CREATED = 'order_created'
    PAYMENT_RECEIVED = 'payment_received'
    ORDER_READY = 'order_ready'
    ORDER_CANCELLED = 'order_cancelled'
    CUSTOM = 'custom'
    TEMPLATE_CHOICES = [
        (ORDER_CREATED, 'Pedido recibido'),
        (PAYMENT_RECEIVED, 'Seña confirmada'),
        (ORDER_READY, 'Pedido listo'),
        (ORDER_CANCELLED, 'Pedido cancelado'),
        (CUSTOM, 'Mensaje personalizado'),
    ]

    PENDING = 'pending'
    QUEUED = 'queued'
    SENT = 'sent'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (PENDING, 'Pendiente'),
        (QUEUED, 'En n8n'),
        (SENT, 'Enviado'),
        (FAILED, 'Falló'),
        (SKIPPED, 'Sin destinatario'),
    ]

    PROVIDER_N8N = 'n8n'
    PROVIDER_DJANGO = 'django'
    PROVIDER_CHOICES = [(PROVIDER_N8N, 'n8n'), (PROVIDER_DJANGO, 'Django')]

    EMAIL = 'email'
    CHANNEL_CHOICES = [(EMAIL, 'Email')]

    order = models.ForeignKey(
        'orders.Order', on_delete=models.CASCADE, related_name='message_deliveries'
    )
    template = models.CharField(max_length=30, choices=TEMPLATE_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=EMAIL)
    recipient = models.CharField(max_length=254, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, blank=True)
    error = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    resent_from = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='resends'
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Envío de mensaje'
        verbose_name_plural = 'Envíos de mensajes'

    def __str__(self):
        return f"#{self.order_id} {self.get_template_display()} — {self.get_status_display()}"

from django.db import models
from core.models import TimeStampedModel


class PaymentIntent(TimeStampedModel):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (PENDING, 'Pendiente'),
        (APPROVED, 'Aprobado'),
        (REJECTED, 'Rechazado'),
        (CANCELLED, 'Cancelado'),
        (REFUNDED, 'Reintegrado'),
    ]

    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='payment_intents')
    mp_preference_id = models.CharField(max_length=200, blank=True)
    mp_payment_id = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=PENDING)
    mp_response = models.JSONField(default=dict)

    class Meta:
        db_table = 'intentos_pago'
        verbose_name = 'Intención de pago'
        verbose_name_plural = 'Intenciones de pago'

    def __str__(self):
        return f"Pago #{self.pk} — {self.get_status_display()} — ${self.amount}"


class WebhookEvent(TimeStampedModel):
    mp_id = models.CharField(max_length=200, db_index=True)
    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = 'eventos_webhook_mp'
        verbose_name = 'Evento webhook'
        verbose_name_plural = 'Eventos webhook'

    def __str__(self):
        return f"Webhook {self.topic} — {self.mp_id}"

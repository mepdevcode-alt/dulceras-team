from django.conf import settings
from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel


class Coupon(TimeStampedModel):
    PERCENTAGE = 'percentage'
    FIXED = 'fixed'
    TYPE_CHOICES = [(PERCENTAGE, 'Porcentaje'), (FIXED, 'Monto fijo')]

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(default=0)       # 0 = ilimitado
    uses_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'cupones'
        verbose_name = 'Cupón'
        verbose_name_plural = 'Cupones'

    def __str__(self):
        return self.code

    def is_valid_for(self, subtotal):
        """Retorna (ok: bool, error: str|None)."""
        if not self.is_active:
            return False, 'Cupón inactivo.'
        today = timezone.localdate()
        if self.valid_from and today < self.valid_from:
            return False, 'El cupón todavía no está vigente.'
        if self.valid_until and today > self.valid_until:
            return False, 'El cupón ya venció.'
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False, 'El cupón ya fue utilizado el máximo de veces.'
        if self.min_order_amount > 0 and subtotal < self.min_order_amount:
            return False, f'El monto mínimo para este cupón es ${self.min_order_amount:,.0f}.'
        return True, None

    def compute_discount(self, subtotal):
        if self.discount_type == self.PERCENTAGE:
            return min(subtotal * self.discount_value / 100, subtotal)
        return min(self.discount_value, subtotal)


class Order(TimeStampedModel):
    DRAFT = 'draft'
    PENDING_DEPOSIT = 'pending_deposit'
    DEPOSIT_PAID = 'deposit_paid'
    CONFIRMED = 'confirmed'
    IN_PRODUCTION = 'in_production'
    READY = 'ready'
    OUT_FOR_DELIVERY = 'out_for_delivery'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'
    REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (DRAFT, 'Borrador'),
        (PENDING_DEPOSIT, 'Esperando seña'),
        (DEPOSIT_PAID, 'Seña pagada'),
        (CONFIRMED, 'Confirmado'),
        (IN_PRODUCTION, 'En producción'),
        (READY, 'Listo'),
        (OUT_FOR_DELIVERY, 'En camino'),
        (DELIVERED, 'Entregado'),
        (CANCELLED, 'Cancelado'),
        (REFUNDED, 'Reintegrado'),
    ]

    DELIVERY = 'delivery'
    PICKUP = 'pickup'
    DELIVERY_CHOICES = [
        (DELIVERY, 'Delivery'),
        (PICKUP, 'Retiro en local'),
    ]

    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=DRAFT)
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default=PICKUP)
    delivery_zone = models.ForeignKey(
        'tenants.DeliveryZone', null=True, blank=True, on_delete=models.SET_NULL
    )
    delivery_address = models.ForeignKey(
        'customers.CustomerAddress', null=True, blank=True, on_delete=models.SET_NULL
    )
    required_date = models.DateField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon = models.ForeignKey(
        Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders'
    )
    coupon_code = models.CharField(max_length=50, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'pedidos'
        ordering = ['-created_at']
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'

    def __str__(self):
        return f"Pedido #{self.pk} — {self.customer} ({self.get_status_display()})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'items_pedido'

    def __str__(self):
        return f"{self.quantity}x {self.product_name} — {self.variant_name}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'historial_estados_pedido'
        ordering = ['changed_at']

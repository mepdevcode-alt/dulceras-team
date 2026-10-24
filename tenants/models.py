from django.db import models
from core.models import TimeStampedModel


class BusinessProfile(models.Model):
    """
    Configuración del negocio: un único registro. Usar BusinessProfile.load().
    """
    name = models.CharField(max_length=200, default='')
    address = models.CharField(max_length=500, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    advance_hours_required = models.PositiveIntegerField(default=48)
    deposit_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=50)
    max_orders_per_day = models.PositiveIntegerField(
        default=0,
        help_text='Máximo de pedidos por día. 0 = sin límite.',
    )
    # Branding
    logo_url = models.URLField(blank=True)
    primary_color = models.CharField(max_length=7, default='#3D1A0E')
    accent_color = models.CharField(max_length=7, default='#E8889A')
    bg_color = models.CharField(max_length=7, default='#FDF6EC')

    class Meta:
        db_table = 'configuracion_negocio'
        verbose_name = 'Configuración del negocio'
        verbose_name_plural = 'Configuración del negocio'

    def __str__(self):
        return self.name or 'Configuración del negocio'

    @classmethod
    def load(cls):
        # El registro migrado desde el esquema multi-tenant puede no tener pk=1
        return cls.objects.order_by('pk').first() or cls.objects.create()


class DeliveryZone(TimeStampedModel):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'zonas_envio'
        verbose_name = 'Zona de envío'
        verbose_name_plural = 'Zonas de envío'

    def __str__(self):
        return self.name

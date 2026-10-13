from django.conf import settings
from django.db import models
from core.models import TimeStampedModel


class Customer(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='customer_profile',
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'clientes'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return self.name


class Review(TimeStampedModel):
    customer = models.ForeignKey(
        Customer, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='reviews',
    )
    author_name = models.CharField(max_length=200)
    rating = models.PositiveSmallIntegerField(default=5)
    text = models.TextField()
    is_approved = models.BooleanField(default=False)

    class Meta:
        db_table = 'resenas'
        ordering = ['-created_at']
        verbose_name = 'Reseña'
        verbose_name_plural = 'Reseñas'

    def __str__(self):
        return f"{self.author_name} ({self.rating}★)"


class CustomerAddress(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='addresses')
    street = models.CharField(max_length=300)
    city = models.CharField(max_length=100, default='Buenos Aires')
    neighborhood = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'direcciones_cliente'
        verbose_name = 'Dirección'
        verbose_name_plural = 'Direcciones'

    def __str__(self):
        return f"{self.customer.name} — {self.street}"

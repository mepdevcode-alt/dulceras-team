from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    PLATFORM_OWNER = 'platform_owner'
    TENANT_ADMIN = 'tenant_admin'
    STAFF_VENTAS = 'staff_ventas'
    STAFF_PRODUCCION = 'staff_produccion'
    STAFF_CAJA = 'staff_caja'
    CUSTOMER = 'customer'

    ROLE_CHOICES = [
        (PLATFORM_OWNER, 'Platform Owner'),
        (TENANT_ADMIN, 'Tenant Admin'),
        (STAFF_VENTAS, 'Staff Ventas'),
        (STAFF_PRODUCCION, 'Staff Producción'),
        (STAFF_CAJA, 'Staff Caja'),
        (CUSTOMER, 'Cliente'),
    ]

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=STAFF_VENTAS)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_platform_owner(self):
        return self.role == self.PLATFORM_OWNER

    @property
    def is_tenant_admin(self):
        return self.role == self.TENANT_ADMIN

    @property
    def is_team_member(self):
        """Usuario del negocio o de la plataforma (puede usar el panel admin). Los clientes no."""
        return self.role != self.CUSTOMER

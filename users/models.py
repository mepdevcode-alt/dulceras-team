from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    SUPERADMIN = 'superadmin'
    ADMIN = 'admin'
    STAFF_VENTAS = 'staff_ventas'
    STAFF_PRODUCCION = 'staff_produccion'
    STAFF_CAJA = 'staff_caja'
    CUSTOMER = 'customer'

    ROLE_CHOICES = [
        (SUPERADMIN, 'Superadmin'),
        (ADMIN, 'Administrador'),
        (STAFF_VENTAS, 'Staff Ventas'),
        (STAFF_PRODUCCION, 'Staff Producción'),
        (STAFF_CAJA, 'Staff Caja'),
        (CUSTOMER, 'Cliente'),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=STAFF_VENTAS)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_superadmin(self):
        """Rol técnico por encima del admin: además accede al panel Sistema."""
        return self.role == self.SUPERADMIN

    @property
    def is_admin(self):
        return self.role in (self.SUPERADMIN, self.ADMIN)

    @property
    def is_team_member(self):
        """Usuario del negocio (puede usar el panel admin). Los clientes no."""
        return self.role != self.CUSTOMER

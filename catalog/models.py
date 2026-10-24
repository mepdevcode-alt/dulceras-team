from django.db import models
from core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'categorias'
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    made_to_order = models.BooleanField(
        default=True,
        help_text='Si está activo, se fabrica bajo pedido (sin control de stock). '
                  'Si está desactivado, requiere stock disponible para poder ordenarse.',
    )
    requires_advance_hours = models.PositiveIntegerField(default=48)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'productos'
        ordering = ['sort_order', 'name']
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'variantes_producto'
        ordering = ['sort_order', 'name']
        verbose_name = 'Variante'
        verbose_name_plural = 'Variantes'

    def __str__(self):
        return f"{self.product.name} — {self.name}"

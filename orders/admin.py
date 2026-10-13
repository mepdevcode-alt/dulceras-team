from django.contrib import admin
from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('subtotal',)
    fields = ('product_variant', 'product_name', 'variant_name', 'unit_price', 'quantity', 'subtotal')


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'changed_at', 'notes')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'status', 'delivery_method', 'required_date', 'total', 'created_at')
    list_filter = ('status', 'delivery_method', 'required_date')
    search_fields = ('customer__name', 'customer__phone')
    readonly_fields = ('subtotal', 'total', 'deposit_amount', 'balance_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    date_hierarchy = 'required_date'

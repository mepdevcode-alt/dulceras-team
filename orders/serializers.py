from datetime import date, timedelta

from django.db import transaction
from rest_framework import serializers

from catalog.models import ProductVariant
from customers.models import Customer, CustomerAddress
from tenants.models import BusinessProfile, DeliveryZone
from .models import Coupon, Order, OrderItem, OrderStatusHistory


# ── Cupones ───────────────────────────────────────────────────────────────────

class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = (
            'id', 'code', 'discount_type', 'discount_value',
            'min_order_amount', 'max_uses', 'uses_count',
            'valid_from', 'valid_until', 'is_active', 'created_at',
        )
        read_only_fields = ('uses_count', 'created_at')


# ── Lectura ───────────────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ('id', 'product_name', 'variant_name', 'unit_price', 'quantity', 'subtotal')


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()

    class Meta:
        model = OrderStatusHistory
        fields = ('from_status', 'to_status', 'changed_by', 'changed_at', 'notes')


class OrderCustomerSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)


class OrderListSerializer(serializers.ModelSerializer):
    customer = OrderCustomerSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'status', 'status_display',
            'customer', 'delivery_method', 'delivery_method_display',
            'required_date', 'discount_amount', 'total', 'deposit_amount', 'balance_amount',
            'created_at',
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    customer = OrderCustomerSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_method_display = serializers.CharField(source='get_delivery_method_display', read_only=True)
    delivery_zone_name = serializers.CharField(source='delivery_zone.name', read_only=True, default=None)

    class Meta:
        model = Order
        fields = (
            'id', 'status', 'status_display',
            'customer', 'delivery_method', 'delivery_method_display',
            'delivery_zone', 'delivery_zone_name', 'required_date',
            'subtotal', 'delivery_cost', 'coupon_code', 'discount_amount', 'total',
            'deposit_percentage', 'deposit_amount', 'balance_amount',
            'notes', 'items', 'status_history', 'created_at', 'updated_at',
        )


# ── Checkout público ──────────────────────────────────────────────────────────

class OrderItemInputSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=200)
    customer_phone = serializers.CharField(max_length=50)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default='')

    items = OrderItemInputSerializer(many=True)

    delivery_method = serializers.ChoiceField(choices=Order.DELIVERY_CHOICES)
    delivery_zone_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    required_date = serializers.DateField()

    address_street = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    address_neighborhood = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    notes = serializers.CharField(required=False, allow_blank=True, default='')
    coupon_code = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        profile = BusinessProfile.load()
        errors = {}

        # Validar que items no esté vacío
        items = attrs.get('items', [])
        if not items:
            raise serializers.ValidationError({'items': 'El pedido debe tener al menos un producto.'})

        # Validar variantes, anticipación y stock
        max_advance_hours = 0
        for i, item in enumerate(items):
            try:
                variant = ProductVariant.objects.select_related('product').get(
                    pk=item['variant_id'], is_active=True
                )
                max_advance_hours = max(max_advance_hours, variant.product.requires_advance_hours)
                if not variant.product.made_to_order:
                    if variant.stock_quantity < item['quantity']:
                        available = variant.stock_quantity
                        errors[f'items_{i}_quantity'] = (
                            f'Stock insuficiente para "{variant.product.name} — {variant.name}". '
                            f'Disponible: {available}.'
                        )
            except ProductVariant.DoesNotExist:
                errors[f'items_{i}_variant_id'] = f'Variante {item["variant_id"]} no disponible.'

        if errors:
            raise serializers.ValidationError(errors)

        # Validar fecha mínima (comparación de date con date)
        required_date = attrs['required_date']
        min_date = date.today() + timedelta(days=max_advance_hours // 24 + (1 if max_advance_hours % 24 else 0))
        if required_date < min_date:
            raise serializers.ValidationError({
                'required_date': (
                    f'Se requieren al menos {max_advance_hours} horas de anticipacion. '
                    f'Fecha minima disponible: {min_date}.'
                )
            })

        # Validar límite diario de pedidos
        max_per_day = profile.max_orders_per_day
        if max_per_day > 0:
            orders_that_day = Order.objects.filter(
                required_date=required_date,
            ).exclude(status__in=['cancelled', 'refunded']).count()
            if orders_that_day >= max_per_day:
                raise serializers.ValidationError({
                    'required_date': (
                        f'Ya se alcanzó el límite de {max_per_day} pedido(s) para el '
                        f'{required_date.strftime("%d/%m/%Y")}. Elegí otra fecha.'
                    )
                })

        # Validar entrega
        if attrs['delivery_method'] == Order.DELIVERY:
            if not attrs.get('delivery_zone_id'):
                errors['delivery_zone_id'] = 'La zona de entrega es obligatoria para delivery.'
            if not attrs.get('address_street', '').strip():
                errors['address_street'] = 'La direccion de entrega es obligatoria para delivery.'
            if errors:
                raise serializers.ValidationError(errors)

        return attrs

    @transaction.atomic
    def create(self, validated_data):

        # Cliente: buscar por teléfono (puede haber duplicados) o crear
        customer = (
            Customer.objects
            .filter(phone=validated_data['customer_phone'])
            .order_by('id')
            .first()
        )
        if customer is None:
            customer = Customer.objects.create(
                phone=validated_data['customer_phone'],
                name=validated_data['customer_name'],
                email=validated_data.get('customer_email', ''),
            )

        # Zona y dirección si es delivery
        delivery_address = None
        delivery_zone = None
        delivery_cost = 0

        if validated_data['delivery_method'] == Order.DELIVERY:
            delivery_address = CustomerAddress.objects.create(
                customer=customer,
                street=validated_data['address_street'],
                neighborhood=validated_data.get('address_neighborhood', ''),
            )
            zone_id = validated_data.get('delivery_zone_id')
            if zone_id:
                try:
                    delivery_zone = DeliveryZone.objects.get(pk=zone_id, is_active=True)
                    delivery_cost = delivery_zone.price
                except DeliveryZone.DoesNotExist:
                    pass

        # Recalcular precios desde DB (no confiar en el frontend)
        # select_for_update bloquea las filas de variante para evitar race conditions de stock
        subtotal = 0
        item_rows = []
        for item in validated_data['items']:
            variant = (
                ProductVariant.objects
                .select_related('product')
                .select_for_update()
                .get(pk=item['variant_id'])
            )
            if not variant.product.made_to_order:
                if variant.stock_quantity < item['quantity']:
                    raise serializers.ValidationError({
                        f'items_stock': (
                            f'Stock insuficiente para "{variant.product.name} — {variant.name}". '
                            f'Disponible: {variant.stock_quantity}.'
                        )
                    })
                ProductVariant.objects.filter(pk=variant.pk).update(
                    stock_quantity=variant.stock_quantity - item['quantity']
                )
            line_total = variant.price * item['quantity']
            subtotal += line_total
            item_rows.append({
                'variant': variant,
                'product_name': variant.product.name,
                'variant_name': variant.name,
                'unit_price': variant.price,
                'quantity': item['quantity'],
                'subtotal': line_total,
            })

        deposit_pct = BusinessProfile.load().deposit_percentage

        # Cupón: validar y calcular descuento
        coupon = None
        coupon_code_snapshot = ''
        discount_amount = 0
        raw_code = (validated_data.get('coupon_code', '') or '').strip().upper()
        if raw_code:
            try:
                coupon = Coupon.objects.get(code__iexact=raw_code)
                ok, _err = coupon.is_valid_for(subtotal)
                if ok:
                    discount_amount = float(coupon.compute_discount(subtotal))
                    coupon_code_snapshot = coupon.code
                else:
                    coupon = None
            except Coupon.DoesNotExist:
                pass

        total = subtotal + delivery_cost - discount_amount
        deposit_amount = round(total * deposit_pct / 100, 2)
        balance_amount = total - deposit_amount

        order = Order.objects.create(
            customer=customer,
            status=Order.PENDING_DEPOSIT,
            delivery_method=validated_data['delivery_method'],
            delivery_zone=delivery_zone,
            delivery_address=delivery_address,
            required_date=validated_data['required_date'],
            subtotal=subtotal,
            delivery_cost=delivery_cost,
            coupon=coupon,
            coupon_code=coupon_code_snapshot,
            discount_amount=discount_amount,
            total=total,
            deposit_percentage=deposit_pct,
            deposit_amount=deposit_amount,
            balance_amount=balance_amount,
            notes=validated_data.get('notes', ''),
        )

        if coupon:
            Coupon.objects.filter(pk=coupon.pk).update(uses_count=coupon.uses_count + 1)

        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product_variant=row['variant'],
                product_name=row['product_name'],
                variant_name=row['variant_name'],
                unit_price=row['unit_price'],
                quantity=row['quantity'],
                subtotal=row['subtotal'],
            )
            for row in item_rows
        ])

        OrderStatusHistory.objects.create(
            order=order,
            from_status='',
            to_status=Order.PENDING_DEPOSIT,
            changed_by=None,
            notes='Pedido creado via checkout',
        )

        try:
            from notifications.services import notify_new_order
            notify_new_order(order)
        except Exception:
            pass

        return order


# ── Admin: cambio de estado ───────────────────────────────────────────────────

class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import Tenant
from .models import Coupon, Order, OrderItem, OrderStatusHistory


# ── Template views ────────────────────────────────────────────────────────────

def order_confirmation(request, order_id):
    """Página de confirmación post-checkout. Sirve el pedido directo desde la DB."""
    order = get_object_or_404(
        Order.objects.prefetch_related('items'),
        pk=order_id,
    )
    return render(request, 'orders/confirmation.html', {
        'order': order,
        'is_paid': order.status != Order.PENDING_DEPOSIT,
    })
from .serializers import (
    CouponSerializer, OrderCreateSerializer, OrderDetailSerializer,
    OrderListSerializer, OrderStatusUpdateSerializer,
)
from users.permissions import IsTeamMember

ACTIVE_STATUSES = [
    Order.PENDING_DEPOSIT, Order.DEPOSIT_PAID, Order.CONFIRMED,
    Order.IN_PRODUCTION, Order.READY, Order.OUT_FOR_DELIVERY, Order.DELIVERED,
]
PAID_STATUSES = [
    Order.DEPOSIT_PAID, Order.CONFIRMED, Order.IN_PRODUCTION,
    Order.READY, Order.OUT_FOR_DELIVERY, Order.DELIVERED,
]


# ── Público ───────────────────────────────────────────────────────────────────

class PublicDateAvailabilityView(APIView):
    """
    Devuelve fechas no disponibles para los próximos 90 días.
    Usado por el checkout para deshabilitar días llenos.
    """
    permission_classes = [AllowAny]

    def get(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        max_per_day = 0
        advance_hours = 48
        try:
            profile = tenant.profile
            max_per_day = profile.max_orders_per_day
            advance_hours = profile.advance_hours_required
        except Exception:
            pass

        today = timezone.localdate()
        min_date = today + timedelta(hours=advance_hours / 24)
        end_date = today + timedelta(days=90)

        unavailable = []
        if max_per_day:
            counts = (
                Order.objects
                .filter(
                    tenant=tenant,
                    required_date__gte=today,
                    required_date__lte=end_date,
                    status__in=ACTIVE_STATUSES,
                )
                .values('required_date')
                .annotate(count=Count('id'))
                .filter(count__gte=max_per_day)
            )
            unavailable = [str(row['required_date']) for row in counts]

        return Response({
            'min_date': str(min_date),
            'max_per_day': max_per_day,
            'unavailable': unavailable,
        })


class PublicOrderCreateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        serializer = OrderCreateSerializer(
            data=request.data, context={'tenant': tenant, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class PublicOrderDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tenant_slug, pk):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        order = get_object_or_404(
            Order.objects.prefetch_related('items', 'status_history')
                         .select_related('customer', 'delivery_zone'),
            pk=pk, tenant=tenant,
        )
        return Response(OrderDetailSerializer(order).data)


class PublicCouponValidateView(APIView):
    """
    POST /api/public/{slug}/coupons/validate/
    Body: { code, subtotal }
    Responde con el descuento calculado sin aplicarlo (no incrementa uses_count).
    """
    permission_classes = [AllowAny]

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        code = (request.data.get('code', '') or '').strip().upper()
        subtotal = request.data.get('subtotal', 0)

        if not code:
            return Response({'valid': False, 'error': 'Ingresá un código de cupón.'}, status=400)

        try:
            subtotal = float(subtotal)
        except (TypeError, ValueError):
            return Response({'valid': False, 'error': 'Subtotal inválido.'}, status=400)

        try:
            coupon = Coupon.objects.get(tenant=tenant, code__iexact=code)
        except Coupon.DoesNotExist:
            return Response({'valid': False, 'error': 'Cupón no encontrado.'})

        ok, error = coupon.is_valid_for(subtotal)
        if not ok:
            return Response({'valid': False, 'error': error})

        discount = float(coupon.compute_discount(subtotal))
        return Response({
            'valid': True,
            'code': coupon.code,
            'discount_type': coupon.discount_type,
            'discount_value': str(coupon.discount_value),
            'discount_amount': discount,
            'final_subtotal': subtotal - discount,
        })


# ── Admin ─────────────────────────────────────────────────────────────────────

def _restore_stock(order):
    from catalog.models import ProductVariant
    for item in order.items.select_related('product_variant__product').all():
        variant = item.product_variant
        if variant and not variant.product.made_to_order:
            ProductVariant.objects.filter(pk=variant.pk).update(
                stock_quantity=variant.stock_quantity + item.quantity
            )


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeamMember]
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = (
            Order.objects
            .select_related('customer', 'delivery_zone', 'tenant')
            .prefetch_related('items', 'status_history')
            .order_by('-created_at')
        )
        if not user.is_platform_owner:
            qs = qs.filter(tenant=user.tenant)
        else:
            slug = self.request.query_params.get('tenant')
            if slug:
                qs = qs.filter(tenant__slug=slug)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        date_filter = self.request.query_params.get('date')
        if date_filter:
            qs = qs.filter(required_date=date_filter)

        search = self.request.query_params.get('search') or self.request.query_params.get('customer')
        if search:
            qs = qs.filter(
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search) |
                Q(customer__email__icontains=search)
            )

        ordering = self.request.query_params.get('ordering')
        if ordering in ('id', '-id', 'created_at', '-created_at', 'required_date', '-required_date', 'customer__name', '-customer__name'):
            qs = qs.order_by(ordering)

        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderListSerializer

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        today = timezone.localdate()
        qs = self.get_queryset()
        active = ['confirmed', 'in_production', 'ready', 'out_for_delivery']
        revenue_qs = self.get_queryset().filter(
            status__in=[*active, 'delivered'],
            created_at__year=today.year,
            created_at__month=today.month,
        )
        from customers.models import Customer
        return Response({
            'pending_deposit': qs.filter(status='pending_deposit').count(),
            'deposit_paid': qs.filter(status='deposit_paid').count(),
            'active': qs.filter(status__in=active).count(),
            'today_orders': qs.filter(required_date=today).count(),
            'orders_month': qs.filter(created_at__year=today.year, created_at__month=today.month).count(),
            'monthly_revenue': float(revenue_qs.aggregate(t=Sum('total'))['t'] or 0),
            'total_customers': Customer.objects.filter(tenant=request.user.tenant).count(),
        })

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response({'detail': 'Se requiere una lista de IDs.'}, status=400)
        qs = self.get_queryset().filter(pk__in=ids)
        # PaymentIntent tiene on_delete=PROTECT → borrar primero
        from payments.models import PaymentIntent
        PaymentIntent.objects.filter(order__in=qs).delete()
        count = qs.count()
        qs.delete()
        return Response({'deleted': count})

    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['status']
        notes = serializer.validated_data.get('notes', '')
        prev_status = order.status

        OrderStatusHistory.objects.create(
            order=order,
            from_status=prev_status,
            to_status=new_status,
            changed_by=request.user,
            notes=notes,
        )
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])

        if new_status in (Order.CANCELLED, Order.REFUNDED) and prev_status not in (Order.CANCELLED, Order.REFUNDED):
            _restore_stock(order)

        try:
            from notifications.services import notify_order_status
            notify_order_status(order.tenant, order, prev_status, new_status, request.user)
        except Exception:
            pass

        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def messages(self, request, pk=None):
        from notifications import n8n
        from notifications.serializers import MessageDeliverySerializer, SendOrderMessageSerializer

        order = self.get_object()

        if request.method == 'GET':
            deliveries = order.message_deliveries.select_related('triggered_by')
            return Response(MessageDeliverySerializer(deliveries, many=True).data)

        serializer = SendOrderMessageSerializer(data=request.data, context={'order': order})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        delivery = n8n.send_order_event(
            order.tenant, order, n8n.MESSAGE_REQUESTED, data['template'],
            subject=data['subject'], message=data['message'],
            triggered_by=request.user, resent_from=data.get('original'),
        )
        delivery.refresh_from_db()
        return Response(MessageDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)

    def _get_tenant(self):
        user = self.request.user
        if user.is_platform_owner:
            slug = self.request.query_params.get('tenant')
            if slug:
                return get_object_or_404(Tenant, slug=slug, is_active=True)
            return user.tenant  # fallback al tenant propio del platform_owner
        return user.tenant

    @action(detail=False, methods=['get'], url_path='calendar')
    def calendar(self, request):
        """Pedidos agrupados por día para un mes (para la vista calendario del admin)."""
        month_str = request.query_params.get('month', timezone.localdate().strftime('%Y-%m'))
        try:
            year, month = map(int, month_str.split('-'))
        except (ValueError, AttributeError):
            return Response({'error': 'Formato inválido. Usar YYYY-MM.'}, status=400)

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)

        max_per_day = 0
        try:
            max_per_day = tenant.profile.max_orders_per_day
        except Exception:
            pass

        orders = (
            Order.objects
            .filter(
                tenant=tenant,
                required_date__year=year,
                required_date__month=month,
                status__in=ACTIVE_STATUSES,
            )
            .select_related('customer')
            .order_by('required_date', 'created_at')
        )

        by_date = defaultdict(list)
        for order in orders:
            by_date[str(order.required_date)].append({
                'id': order.id,
                'customer': order.customer.name,
                'status': order.status,
                'status_display': order.get_status_display(),
                'total': str(order.total),
            })

        return Response({
            'month': month_str,
            'max_per_day': max_per_day,
            'days': {
                date: {'count': len(items), 'orders': items}
                for date, items in by_date.items()
            },
        })

    @action(detail=False, methods=['get'], url_path='production')
    def production(self, request):
        """Lista de producción detallada para una fecha: pedidos + resumen de items."""
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({'error': 'Parámetro date requerido (YYYY-MM-DD).'}, status=400)

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)

        orders = (
            Order.objects
            .filter(
                tenant=tenant,
                required_date=date_str,
                status__in=ACTIVE_STATUSES,
            )
            .select_related('customer', 'delivery_zone')
            .prefetch_related('items')
            .order_by('created_at')
        )

        product_totals = defaultdict(lambda: defaultdict(int))
        for order in orders:
            for item in order.items.all():
                product_totals[item.product_name][item.variant_name] += item.quantity

        summary = sorted([
            {
                'product': product,
                'variants': [
                    {'name': v, 'quantity': q}
                    for v, q in sorted(variants.items())
                ],
                'total_units': sum(variants.values()),
            }
            for product, variants in product_totals.items()
        ], key=lambda x: x['product'])

        return Response({
            'date': date_str,
            'orders': OrderDetailSerializer(orders, many=True).data,
            'production_summary': summary,
        })

    @action(detail=False, methods=['get'], url_path='reports')
    def reports(self, request):  # noqa: C901
        """
        Reporte financiero y operativo por período.
        ?period=today|week|month|all  (default: month)
        """
        period = request.query_params.get('period', 'month')
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)

        today = timezone.localdate()
        if period == 'today':
            from_date, to_date = today, today
        elif period == 'week':
            from_date = today - timedelta(days=today.weekday())
            to_date = today
        elif period == 'month':
            from_date = today.replace(day=1)
            to_date = today
        else:
            from_date, to_date = None, None

        def date_qs(qs):
            if from_date:
                qs = qs.filter(created_at__date__gte=from_date)
            if to_date:
                qs = qs.filter(created_at__date__lte=to_date)
            return qs

        base = date_qs(Order.objects.filter(tenant=tenant, status__in=ACTIVE_STATUSES))
        paid = Q(status__in=PAID_STATUSES)
        unpaid_balance = Q(status__in=[s for s in PAID_STATUSES if s != Order.DELIVERED])

        # ── Ingresos ─────────────────────────────────────────────────────────
        totals = base.aggregate(
            total=Sum('total'),
            deposits=Sum('deposit_amount', filter=paid),
            balance_pending=Sum('balance_amount', filter=unpaid_balance),
            order_count=Count('id'),
        )

        # ── Por estado ────────────────────────────────────────────────────────
        status_display = dict(Order.STATUS_CHOICES)
        by_status = [
            {
                'status': row['status'],
                'label': status_display.get(row['status'], row['status']),
                'count': row['count'],
            }
            for row in base.values('status').annotate(count=Count('id')).order_by('-count')
        ]

        # ── Productos más vendidos ────────────────────────────────────────────
        item_filters = {'order__tenant': tenant, 'order__status__in': PAID_STATUSES}
        if from_date:
            item_filters['order__created_at__date__gte'] = from_date
        if to_date:
            item_filters['order__created_at__date__lte'] = to_date
        item_base = OrderItem.objects.filter(**item_filters)
        top_products = [
            {**row, 'revenue': float(row['revenue'] or 0)}
            for row in item_base
            .values('product_name', 'variant_name')
            .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
            .order_by('-qty')[:10]
        ]

        # ── Por zona ──────────────────────────────────────────────────────────
        pickup = base.filter(delivery_method=Order.PICKUP).aggregate(
            count=Count('id'), revenue=Sum('total')
        )
        by_zone = [
            {'zone': 'Retiro en local', 'count': pickup['count'] or 0,
             'revenue': float(pickup['revenue'] or 0)},
            *[
                {'zone': row['delivery_zone__name'] or 'Sin zona',
                 'count': row['count'],
                 'revenue': float(row['revenue'] or 0)}
                for row in base.filter(delivery_method=Order.DELIVERY)
                .values('delivery_zone__name')
                .annotate(count=Count('id'), revenue=Sum('total'))
                .order_by('-count')
            ],
        ]

        # ── Ventas diarias ────────────────────────────────────────────────────
        daily = [
            {'date': str(row['day']), 'count': row['count'], 'revenue': float(row['revenue'] or 0)}
            for row in date_qs(Order.objects.filter(tenant=tenant, status__in=PAID_STATUSES))
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'), revenue=Sum('total'))
            .order_by('day')
        ]

        # ── Clientes nuevos vs recurrentes ────────────────────────────────────
        customer_ids_in_period = list(base.values_list('customer_id', flat=True).distinct())
        unique_count = len(customer_ids_in_period)
        if from_date and customer_ids_in_period:
            returning_ids = set(
                Order.objects.filter(
                    tenant=tenant,
                    customer_id__in=customer_ids_in_period,
                    created_at__date__lt=from_date,
                ).values_list('customer_id', flat=True)
            )
            returning_count = len(returning_ids)
            new_count = unique_count - returning_count
        else:
            new_count = unique_count
            returning_count = 0
        customers_insight = {
            'unique': unique_count,
            'new': new_count,
            'returning': returning_count,
        }

        # ── Días pico (por día de la semana) ──────────────────────────────────
        from collections import defaultdict as _defaultdict
        _day_data = _defaultdict(lambda: {'count': 0, 'revenue': 0.0})
        for row in base.values('required_date', 'total'):
            if row['required_date']:
                dow = row['required_date'].weekday()  # 0=Lun, 6=Dom
                _day_data[dow]['count'] += 1
                _day_data[dow]['revenue'] += float(row['total'] or 0)
        _day_labels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        by_day_of_week = [
            {'day': i, 'label': _day_labels[i], **_day_data.get(i, {'count': 0, 'revenue': 0.0})}
            for i in range(7)
        ]

        # ── Uso de cupones ────────────────────────────────────────────────────
        _coupon_base = base.filter(coupon_code__gt='')
        _coupon_agg = _coupon_base.aggregate(
            count=Count('id'),
            total_discount=Sum('discount_amount'),
        )
        _top_coupons = list(
            _coupon_base.values('coupon_code')
            .annotate(uses=Count('id'), discount_total=Sum('discount_amount'))
            .order_by('-uses')[:5]
        )
        coupon_stats = {
            'orders_with_coupon': _coupon_agg['count'] or 0,
            'total_discount': float(_coupon_agg['total_discount'] or 0),
            'top_coupons': [
                {
                    'code': c['coupon_code'],
                    'uses': c['uses'],
                    'total_discount': float(c['discount_total'] or 0),
                }
                for c in _top_coupons
            ],
        }

        return Response({
            'period': period,
            'from_date': str(from_date) if from_date else None,
            'to_date': str(to_date) if to_date else None,
            'revenue': {
                'total': float(totals['total'] or 0),
                'deposits_collected': float(totals['deposits'] or 0),
                'balance_pending': float(totals['balance_pending'] or 0),
                'order_count': totals['order_count'] or 0,
            },
            'by_status': by_status,
            'top_products': top_products,
            'by_zone': by_zone,
            'daily': daily,
            'customers_insight': customers_insight,
            'by_day_of_week': by_day_of_week,
            'coupon_stats': coupon_stats,
        })


class AdminCouponViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = CouponSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Coupon.objects.order_by('-created_at')
        if not user.is_platform_owner:
            qs = qs.filter(tenant=user.tenant)
        return qs

    def perform_create(self, serializer):
        code = (serializer.validated_data.get('code', '') or '').upper()
        serializer.save(tenant=self.request.user.tenant, code=code)

    def perform_update(self, serializer):
        if 'code' in serializer.validated_data:
            serializer.validated_data['code'] = serializer.validated_data['code'].upper()
        serializer.save()

    @action(detail=True, methods=['post'], url_path='toggle')
    def toggle_active(self, request, pk=None):
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=['is_active', 'updated_at'])
        return Response(CouponSerializer(coupon).data)

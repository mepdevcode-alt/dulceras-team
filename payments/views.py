from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.views import TenantFilterMixin
from orders.models import Order, OrderStatusHistory
from tenants.models import Tenant
from .models import PaymentIntent, WebhookEvent
from .serializers import PaymentIntentSerializer, WebhookEventSerializer
from .services import build_mp_preference, get_mp_sdk
from users.permissions import IsTeamMember


# ── Template views ────────────────────────────────────────────────────────────

def payment_success(request):
    return render(request, 'payments/success.html')

def payment_failure(request):
    order_id = request.GET.get('order_id', '')
    return render(request, 'payments/failure.html', {'order_id': order_id})

def payment_pending(request):
    order_id = request.GET.get('order_id', '')
    return render(request, 'payments/pending.html', {'order_id': order_id})


# ── Público ───────────────────────────────────────────────────────────────────

class InitiatePaymentView(APIView):
    """
    Crea un PaymentIntent y (si hay token) una preferencia en Mercado Pago.
    El frontend redirige al usuario a init_point para completar el pago.
    """
    permission_classes = [AllowAny]

    def post(self, request, tenant_slug, order_id):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        order = get_object_or_404(
            Order, pk=order_id, tenant=tenant, status=Order.PENDING_DEPOSIT
        )

        intent = PaymentIntent.objects.create(
            tenant=tenant,
            order=order,
            amount=order.deposit_amount,
        )

        sdk = get_mp_sdk(tenant)
        if not sdk:
            return Response(
                {
                    'payment_intent_id': intent.id,
                    'init_point': None,
                    'sandbox': True,
                    'amount': str(intent.amount),
                    'detail': 'Mercado Pago no configurado. '
                              'Configure MERCADOPAGO_ACCESS_TOKEN para pagos reales.',
                },
                status=status.HTTP_201_CREATED,
            )

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        notification_url = (
            getattr(settings, 'MP_WEBHOOK_URL', '')
            or request.build_absolute_uri(f'/api/public/{tenant_slug}/webhooks/mp/')
        )
        preference_data = build_mp_preference(intent, tenant_slug, frontend_url, notification_url)

        try:
            result = sdk.preference().create(preference_data)
            mp_status = result.get('status', 0)
            preference = result['response']

            if mp_status not in (200, 201) or not preference.get('id'):
                intent.status = PaymentIntent.CANCELLED
                intent.mp_response = preference
                intent.save(update_fields=['status', 'mp_response', 'updated_at'])
                return Response(
                    {'detail': 'Mercado Pago rechazó la preferencia.', 'mp_error': preference},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            intent.mp_preference_id = preference.get('id', '')
            intent.mp_response = preference
            intent.save(update_fields=['mp_preference_id', 'mp_response', 'updated_at'])
            return Response(
                {
                    'payment_intent_id': intent.id,
                    'init_point': preference.get('init_point'),
                    'sandbox_init_point': preference.get('sandbox_init_point'),
                    'amount': str(intent.amount),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            intent.status = PaymentIntent.CANCELLED
            intent.mp_response = {'error': str(exc)}
            intent.save(update_fields=['status', 'mp_response', 'updated_at'])
            return Response(
                {'detail': 'Error al crear preferencia de pago.', 'error': str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PaymentStatusView(APIView):
    """Consulta el estado del último PaymentIntent de un pedido."""
    permission_classes = [AllowAny]

    def get(self, request, tenant_slug, order_id):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        order = get_object_or_404(Order, pk=order_id, tenant=tenant)
        intent = order.payment_intents.order_by('-created_at').first()
        if not intent:
            return Response({'status': None, 'detail': 'Sin intentos de pago registrados.'})
        return Response(PaymentIntentSerializer(intent).data)


class MercadoPagoWebhookView(APIView):
    """
    Receptor de notificaciones de Mercado Pago.
    - GET: validación de URL por MP (siempre 200)
    - POST: notificación de evento (idempotente via mp_id)

    El estado del pago se confirma consultando la API de MP,
    NUNCA confiando solo en los query params del redirect.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    # TODO: validar firma X-MP-Signature cuando MP la envíe

    def get(self, request, tenant_slug):
        return Response({'status': 'ok'})

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)

        data = request.data
        topic = data.get('type') or request.query_params.get('topic', 'unknown')
        mp_id = str(
            (data.get('data') or {}).get('id')
            or request.query_params.get('id', '')
        )

        if not mp_id or mp_id == 'None':
            return Response({'status': 'ignored'})

        # Idempotencia: registrar evento antes de procesar
        event, created = WebhookEvent.objects.get_or_create(
            mp_id=mp_id,
            tenant=tenant,
            defaults={'topic': topic, 'payload': data},
        )
        if not created and event.processed:
            return Response({'status': 'already_processed'})

        sdk = get_mp_sdk(tenant)
        if sdk and topic == 'payment':
            try:
                payment_response = sdk.payment().get(mp_id)
                payment_data = payment_response.get('response', {})
                mp_status = payment_data.get('status')
                external_ref = payment_data.get('external_reference')

                if external_ref and str(external_ref).startswith('sub_'):
                    # Subscription payment
                    try:
                        from tenants.models import Subscription
                        from django.utils import timezone
                        from datetime import timedelta
                        sub_id = int(str(external_ref)[4:])
                        sub = Subscription.objects.get(pk=sub_id, tenant=tenant)
                        if mp_status == 'approved':
                            sub.status = Subscription.ACTIVE
                            sub.last_payment_mp_id = mp_id
                            sub.current_period_end = timezone.now() + timedelta(days=30)
                            sub.save(update_fields=['status', 'last_payment_mp_id', 'current_period_end', 'updated_at'])
                    except (Subscription.DoesNotExist, ValueError):
                        pass

                elif external_ref:
                    try:
                        intent = (
                            PaymentIntent.objects
                            .filter(order_id=int(external_ref), tenant=tenant)
                            .order_by('-created_at')
                            .first()
                        )
                        if not intent:
                            raise PaymentIntent.DoesNotExist
                        status_map = {
                            'approved': PaymentIntent.APPROVED,
                            'rejected': PaymentIntent.REJECTED,
                            'cancelled': PaymentIntent.CANCELLED,
                            'refunded': PaymentIntent.REFUNDED,
                        }
                        intent.status = status_map.get(mp_status, PaymentIntent.PENDING)
                        intent.mp_payment_id = mp_id
                        intent.mp_response = payment_data
                        intent.save(update_fields=['status', 'mp_payment_id', 'mp_response', 'updated_at'])

                        if mp_status == 'approved':
                            order = intent.order
                            if order.status == Order.PENDING_DEPOSIT:
                                prev_status = order.status
                                order.status = Order.DEPOSIT_PAID
                                order.save(update_fields=['status', 'updated_at'])
                                OrderStatusHistory.objects.create(
                                    order=order,
                                    from_status=prev_status,
                                    to_status=Order.DEPOSIT_PAID,
                                    changed_by=None,
                                    notes=f'Seña aprobada via Mercado Pago (mp_id={mp_id})',
                                )
                                try:
                                    from notifications.services import notify_payment_received
                                    notify_payment_received(tenant, order, mp_payment_id=mp_id)
                                except Exception:
                                    pass
                    except (PaymentIntent.DoesNotExist, ValueError):
                        pass

                event.processed = True
                event.processed_at = timezone.now()
                event.save(update_fields=['processed', 'processed_at'])

            except Exception as exc:
                event.error = str(exc)
                event.save(update_fields=['error'])

        return Response({'status': 'received'})


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminPaymentViewSet(TenantFilterMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = PaymentIntentSerializer
    queryset = (
        PaymentIntent.objects
        .select_related('order', 'tenant')
        .order_by('-created_at')
    )

    def get_queryset(self):
        qs = super().get_queryset()
        if s := self.request.query_params.get('status'):
            qs = qs.filter(status=s)
        if o := self.request.query_params.get('order'):
            qs = qs.filter(order_id=o)
        return qs


class AdminWebhookViewSet(TenantFilterMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = WebhookEventSerializer
    queryset = WebhookEvent.objects.order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        if p := self.request.query_params.get('processed'):
            qs = qs.filter(processed=p.lower() == 'true')
        return qs

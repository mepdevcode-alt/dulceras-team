import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.views import TenantFilterMixin
from .models import MessageDelivery, Notification, WhatsAppLog
from .serializers import NotificationSerializer, WhatsAppLogSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Notificaciones personales del usuario autenticado (la campanita).
    Cada usuario solo ve las suyas — no usa TenantFilterMixin.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        if is_read := self.request.query_params.get('is_read'):
            qs = qs.filter(is_read=is_read.lower() == 'true')
        return qs

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = (
            Notification.objects
            .filter(recipient=request.user, is_read=False)
            .update(is_read=True)
        )
        return Response({'marked_read': updated})


class WhatsAppLogViewSet(TenantFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Log de mensajes WhatsApp enviados — solo lectura para admins."""
    permission_classes = [IsAuthenticated]
    serializer_class = WhatsAppLogSerializer
    queryset = WhatsAppLog.objects.select_related('order').order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        if s := self.request.query_params.get('sent'):
            qs = qs.filter(sent=s.lower() == 'true')
        if o := self.request.query_params.get('order'):
            qs = qs.filter(order_id=o)
        return qs


class N8nDeliveryCallbackView(APIView):
    """
    n8n informa el resultado de un email: POST {status: 'sent'|'failed', error?}.
    Autenticado con el mismo secreto compartido del webhook (N8N_WEBHOOK_SECRET).
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    FINAL = {MessageDelivery.SENT, MessageDelivery.FAILED}

    def post(self, request, delivery_id):
        secret = settings.N8N_WEBHOOK_SECRET
        received = request.headers.get(settings.N8N_WEBHOOK_SECRET_HEADER, '')
        if not secret or not hmac.compare_digest(received.encode(), secret.encode()):
            return Response({'detail': 'No autorizado.'}, status=403)

        new_status = request.data.get('status')
        if new_status not in self.FINAL:
            return Response({'detail': "status debe ser 'sent' o 'failed'."}, status=400)

        delivery = get_object_or_404(MessageDelivery, pk=delivery_id)
        fields = {
            'status': new_status,
            'provider': MessageDelivery.PROVIDER_N8N,
            'error': str(request.data.get('error') or '')[:2000] if new_status == MessageDelivery.FAILED else '',
            'updated_at': timezone.now(),
        }
        if new_status == MessageDelivery.SENT:
            fields['sent_at'] = timezone.now()
        # Solo envíos en curso: no pisar un resultado final (ej. fallback de Django).
        updated = MessageDelivery.objects.filter(
            pk=delivery.pk, status__in=[MessageDelivery.PENDING, MessageDelivery.QUEUED],
        ).update(**fields)
        return Response({'id': delivery.pk, 'updated': bool(updated)})

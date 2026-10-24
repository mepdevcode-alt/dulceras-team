"""
Panel Sistema (/api/superadmin/...): registros técnicos de solo lectura para el rol superadmin.
"""
from rest_framework import serializers, viewsets

from notifications.models import MessageDelivery
from notifications.serializers import MessageDeliverySerializer
from payments.models import WebhookEvent
from payments.serializers import WebhookEventSerializer
from users.permissions import IsSuperadmin
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ('id', 'username', 'action', 'model_name', 'object_id', 'changes', 'ip_address', 'created_at')
        read_only_fields = fields


class SystemWebhookViewSet(viewsets.ReadOnlyModelViewSet):
    """Notificaciones recibidas de Mercado Pago (idempotencia por mp_id)."""
    permission_classes = [IsSuperadmin]
    serializer_class = WebhookEventSerializer

    def get_queryset(self):
        qs = WebhookEvent.objects.order_by('-created_at')
        if p := self.request.query_params.get('processed'):
            qs = qs.filter(processed=p.lower() == 'true')
        return qs


class SystemDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """Emails a clientes de todos los pedidos (vía n8n o Django)."""
    permission_classes = [IsSuperadmin]

    class Serializer(MessageDeliverySerializer):
        class Meta(MessageDeliverySerializer.Meta):
            fields = ('order', *MessageDeliverySerializer.Meta.fields)
            read_only_fields = fields

    serializer_class = Serializer

    def get_queryset(self):
        qs = MessageDelivery.objects.select_related('triggered_by').order_by('-created_at')
        if s := self.request.query_params.get('status'):
            qs = qs.filter(status=s)
        return qs


class SystemAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsSuperadmin]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related('user').order_by('-created_at')

from rest_framework import serializers
from .models import MessageDelivery, Notification, WhatsAppLog
from .services import wa_link


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True, default=None)

    class Meta:
        model = Notification
        fields = (
            'id', 'type', 'type_display', 'title', 'message',
            'is_read', 'order_id', 'created_at',
        )
        read_only_fields = ('type', 'type_display', 'title', 'message', 'order_id', 'created_at')


class WhatsAppLogSerializer(serializers.ModelSerializer):
    wa_link = serializers.SerializerMethodField()

    def get_wa_link(self, obj):
        if not obj.phone:
            return None
        return wa_link(obj.phone, obj.message)

    class Meta:
        model = WhatsAppLog
        fields = ('id', 'phone', 'message', 'order', 'sent', 'sent_at', 'error', 'wa_link', 'created_at')
        read_only_fields = fields


class MessageDeliverySerializer(serializers.ModelSerializer):
    template_display = serializers.CharField(source='get_template_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    triggered_by_name = serializers.SerializerMethodField()

    def get_triggered_by_name(self, obj):
        user = obj.triggered_by
        if not user:
            return None
        return user.get_full_name() or user.username

    class Meta:
        model = MessageDelivery
        fields = (
            'id', 'template', 'template_display', 'channel', 'recipient', 'subject', 'message',
            'status', 'status_display', 'provider', 'error', 'triggered_by_name',
            'resent_from', 'created_at', 'sent_at',
        )
        read_only_fields = fields


class SendOrderMessageSerializer(serializers.Serializer):
    """Envío manual desde el panel: plantilla, mensaje libre o reenvío de uno anterior."""
    template = serializers.ChoiceField(choices=MessageDelivery.TEMPLATE_CHOICES, required=False)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)
    message = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    resend_of = serializers.IntegerField(required=False)

    # Plantilla -> estados del pedido en los que tiene sentido enviarla
    ALLOWED_STATUSES = {
        MessageDelivery.PAYMENT_RECEIVED: {
            'deposit_paid', 'confirmed', 'in_production', 'ready', 'out_for_delivery', 'delivered',
        },
        MessageDelivery.ORDER_READY: {'ready'},
        MessageDelivery.ORDER_CANCELLED: {'cancelled'},
    }

    def validate(self, attrs):
        order = self.context['order']
        resend_of = attrs.get('resend_of')
        if resend_of:
            original = order.message_deliveries.filter(pk=resend_of).first()
            if not original:
                raise serializers.ValidationError({'resend_of': 'Envío no encontrado para este pedido.'})
            attrs.update(template=original.template, subject=original.subject,
                         message=original.message, original=original)

        template = attrs.get('template')
        if not template:
            raise serializers.ValidationError({'template': 'Elegí una plantilla.'})

        if template == MessageDelivery.CUSTOM:
            if not attrs.get('subject', '').strip():
                raise serializers.ValidationError({'subject': 'Escribí un asunto.'})
            if not attrs.get('message', '').strip():
                raise serializers.ValidationError({'message': 'Escribí el mensaje.'})
        else:
            attrs['subject'] = attrs['message'] = ''

        allowed = self.ALLOWED_STATUSES.get(template)
        if allowed and order.status not in allowed:
            label = dict(MessageDelivery.TEMPLATE_CHOICES)[template]
            raise serializers.ValidationError({
                'template': f'No se puede enviar "{label}" con el pedido en estado "{order.get_status_display()}".'
            })

        if not (order.customer.email or '').strip():
            raise serializers.ValidationError({'detail': 'El cliente no tiene email cargado.'})
        return attrs

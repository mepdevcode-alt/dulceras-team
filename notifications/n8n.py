"""
Integración con n8n para mensajes de pedidos (emails al cliente, avisos al equipo).

n8n corre en la misma máquina y no se expone a internet: Django le envía los
eventos por POST a un webhook local y n8n se encarga del envío. Cada email al
cliente queda registrado en `MessageDelivery`; n8n informa el resultado
llamando a `/api/n8n/deliveries/<id>/status/` (ver views.N8nDeliveryCallbackView).

- Si N8N_WEBHOOK_URL está vacío, la integración está apagada y los emails los
  manda Django (email_service).
- Si n8n no responde o devuelve error, Django manda su propio email como fallback.

Regla: nunca bloquear ni romper el flujo principal (checkout, webhook de pago).
"""
import logging
import threading

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from tenants.models import BusinessProfile
from . import email_service
from .models import MessageDelivery

logger = logging.getLogger(__name__)

# Eventos que recibe n8n
ORDER_CREATED = 'order_created'
PAYMENT_RECEIVED = 'payment_received'
ORDER_STATUS_CHANGED = 'order_status_changed'
MESSAGE_REQUESTED = 'message_requested'  # envío manual desde el panel admin

# Fallback de Django por plantilla: delivery -> bool
DJANGO_SENDERS = {
    MessageDelivery.ORDER_CREATED: lambda d: email_service.send_order_confirmation(d.order),
    MessageDelivery.PAYMENT_RECEIVED: lambda d: email_service.send_payment_confirmed(d.order),
    MessageDelivery.ORDER_READY: lambda d: email_service.send_order_ready(d.order),
    MessageDelivery.ORDER_CANCELLED: lambda d: email_service.send_order_cancelled(d.order),
    MessageDelivery.CUSTOM: lambda d: email_service.send_custom_message(d.order, d.subject, d.message),
}


def is_enabled():
    return bool(getattr(settings, 'N8N_WEBHOOK_URL', ''))


def _money(value):
    return float(value or 0)


def _business_payload():
    business = BusinessProfile.load()
    return {
        'name': business.name,
        'email': business.email,
        'phone': business.phone,
        'whatsapp': business.whatsapp,
        'instagram': business.instagram,
        'logo_url': business.logo_url,
        'primary_color': business.primary_color or '#3D1A0E',
        'accent_color': business.accent_color or '#E8889A',
        'bg_color': business.bg_color or '#FDF6EC',
    }


def _address_payload(address):
    if not address:
        return None
    return {
        'street': address.street,
        'neighborhood': address.neighborhood,
        'city': address.city,
        'notes': address.notes,
    }


def _callback_url(delivery):
    base = (getattr(settings, 'N8N_CALLBACK_BASE_URL', '') or settings.FRONTEND_URL).rstrip('/')
    return f'{base}/api/n8n/deliveries/{delivery.pk}/status/'


def _delivery_payload(delivery):
    if not delivery or delivery.status == MessageDelivery.SKIPPED:
        return None
    return {
        'id': delivery.pk,
        'template': delivery.template,
        'recipient': delivery.recipient,
        'subject': delivery.subject,
        'message': delivery.message,
        'callback_url': _callback_url(delivery),
    }


def build_order_payload(order, event, delivery=None, **extra):
    frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    customer = order.customer
    return {
        'event': event,
        'sent_at': timezone.now().isoformat(),
        'business': _business_payload(),
        'order': {
            'id': order.pk,
            'status': order.status,
            'status_display': order.get_status_display(),
            'required_date': order.required_date.isoformat(),
            'required_date_display': order.required_date.strftime('%d/%m/%Y'),
            'delivery_method': order.delivery_method,
            'delivery_method_display': order.get_delivery_method_display(),
            'delivery_address': _address_payload(order.delivery_address),
            'subtotal': _money(order.subtotal),
            'delivery_cost': _money(order.delivery_cost),
            'discount_amount': _money(order.discount_amount),
            'coupon_code': order.coupon_code,
            'total': _money(order.total),
            'deposit_percentage': _money(order.deposit_percentage),
            'deposit_amount': _money(order.deposit_amount),
            'balance_amount': _money(order.balance_amount),
            'notes': order.notes,
            'url': f'{frontend_url}/pedido/{order.pk}' if frontend_url else '',
            'items': [
                {
                    'product_name': item.product_name,
                    'variant_name': item.variant_name,
                    'quantity': item.quantity,
                    'unit_price': _money(item.unit_price),
                    'subtotal': _money(item.subtotal),
                }
                for item in order.items.all()
            ],
        },
        'customer': {
            'name': customer.name,
            'email': (customer.email or '').strip(),
            'phone': customer.phone,
        },
        'delivery': _delivery_payload(delivery),
        **extra,
    }


def _post(payload):
    headers = {}
    secret = settings.N8N_WEBHOOK_SECRET
    if secret:
        headers[settings.N8N_WEBHOOK_SECRET_HEADER] = secret
    resp = requests.post(
        settings.N8N_WEBHOOK_URL,
        json=payload,
        headers=headers,
        timeout=settings.N8N_TIMEOUT,
    )
    resp.raise_for_status()


def _set_status(delivery, status, provider=None, error=''):
    fields = {'status': status, 'error': error, 'updated_at': timezone.now()}
    if provider:
        fields['provider'] = provider
    if status == MessageDelivery.SENT:
        fields['sent_at'] = timezone.now()
    MessageDelivery.objects.filter(pk=delivery.pk).update(**fields)


def _send_with_django(delivery, error=''):
    ok = False
    try:
        ok = DJANGO_SENDERS[delivery.template](delivery)
    except Exception:
        logger.exception('Email de Django falló (envío #%s)', delivery.pk)
    if ok:
        # Se conserva el motivo del fallback (ej. n8n caído) como dato informativo.
        _set_status(delivery, MessageDelivery.SENT, MessageDelivery.PROVIDER_DJANGO, error)
    else:
        detail = 'El email no se pudo enviar por SMTP (Django).'
        _set_status(delivery, MessageDelivery.FAILED, MessageDelivery.PROVIDER_DJANGO,
                    f'{error} {detail}'.strip())


def _deliver(payload, delivery):
    active = delivery and delivery.status != MessageDelivery.SKIPPED
    if not is_enabled():
        if active:
            _send_with_django(delivery)
        return

    if active:
        # Antes del POST: el callback de n8n puede llegar antes de que _post retorne.
        _set_status(delivery, MessageDelivery.QUEUED, MessageDelivery.PROVIDER_N8N)
    try:
        _post(payload)
    except Exception as exc:
        logger.warning(
            'n8n: no se pudo enviar el evento %s del pedido #%s (%s); usando fallback.',
            payload.get('event'), payload.get('order', {}).get('id'), exc,
        )
        if active:
            _send_with_django(delivery, f'n8n no disponible: {exc}.')


def _deliver_in_thread(payload, delivery):
    try:
        _deliver(payload, delivery)
    except Exception:
        logger.exception('n8n: error inesperado enviando %s', payload.get('event'))
    finally:
        # Este thread usa su propia conexión a la DB: cerrarla al terminar.
        connection.close()


def send_order_event(order, event, template=None, *, subject='', message='',
                     triggered_by=None, resent_from=None, **extra):
    """
    Dispara un evento de pedido. Si `template` está presente, además registra y
    envía un email al cliente con esa plantilla. Devuelve el MessageDelivery
    creado (o None si el evento no lleva email al cliente).

    Si n8n está apagado y no hay plantilla, no hace nada.
    """
    if not template and not is_enabled():
        return None

    delivery = None
    if template:
        recipient = (order.customer.email or '').strip()
        delivery = MessageDelivery.objects.create(
            order=order,
            template=template,
            recipient=recipient,
            subject=subject,
            message=message,
            triggered_by=triggered_by,
            resent_from=resent_from,
            status=MessageDelivery.PENDING if recipient else MessageDelivery.SKIPPED,
            error='' if recipient else 'El cliente no tiene email cargado.',
        )

    try:
        payload = build_order_payload(order, event, delivery=delivery, **extra)
    except Exception:
        logger.exception('n8n: no se pudo armar el payload del pedido #%s', order.pk)
        payload = None

    def send():
        if payload is None:
            # Sin payload no hay n8n: mandar el email con Django.
            if delivery and delivery.status != MessageDelivery.SKIPPED:
                _send_with_django(delivery)
            return
        # Con n8n apagado se envía en el request, como siempre lo hizo Django.
        if settings.N8N_ASYNC and is_enabled():
            threading.Thread(
                target=_deliver_in_thread, args=(payload, delivery), daemon=True,
            ).start()
        else:
            _deliver(payload, delivery)

    transaction.on_commit(send)
    return delivery

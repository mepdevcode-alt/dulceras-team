"""
Servicio de notificaciones. Toda la lógica de creación de notificaciones
y envío de WhatsApp vive aquí para no dispersar lógica de negocio en las vistas.

Regla: nunca bloquear el flujo principal si falla una notificación.
Siempre llamar desde un try/except en el código llamador.
"""
import re
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from .models import MessageDelivery, Notification, WhatsAppLog
from . import n8n

# Cambios de estado que le mandan un email al cliente
STATUS_TEMPLATES = {
    'ready': MessageDelivery.ORDER_READY,
    'cancelled': MessageDelivery.ORDER_CANCELLED,
}


def _normalize_phone(phone: str) -> str:
    """Devuelve el número en formato E.164 sin '+', apto para wa.me."""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0'):
        digits = '54' + digits[1:]
    if len(digits) == 10:
        digits = '549' + digits
    return digits


def wa_link(phone: str, message: str) -> str:
    return f'https://wa.me/{_normalize_phone(phone)}?text={quote(message)}'


# ── Bell in-app ───────────────────────────────────────────────────────────────

def _staff_users(tenant):
    from users.models import User
    return list(
        User.objects.filter(
            tenant=tenant,
            is_active=True,
            role__in=[User.TENANT_ADMIN, User.STAFF_VENTAS, User.STAFF_CAJA],
        )
    )


def _bulk_notify(tenant, notification_type, title, message, order=None):
    users = _staff_users(tenant)
    if not users:
        return
    Notification.objects.bulk_create([
        Notification(
            tenant=tenant,
            recipient=user,
            type=notification_type,
            title=title,
            message=message,
            order=order,
        )
        for user in users
    ])


def notify_new_order(tenant, order):
    _bulk_notify(
        tenant,
        Notification.NEW_ORDER,
        f'Nuevo pedido #{order.pk}',
        (
            f'Cliente: {order.customer.name}. '
            f'Total: ${order.total}. '
            f'Seña: ${order.deposit_amount}. '
            f'Fecha solicitada: {order.required_date.strftime("%d/%m/%Y")}.'
        ),
        order=order,
    )
    _whatsapp_new_order(tenant, order)
    _whatsapp_order_received_customer(tenant, order)
    n8n.send_order_event(tenant, order, n8n.ORDER_CREATED, MessageDelivery.ORDER_CREATED)


def notify_payment_received(tenant, order, mp_payment_id=''):
    _bulk_notify(
        tenant,
        Notification.PAYMENT_RECEIVED,
        f'Seña recibida — Pedido #{order.pk}',
        (
            f'Cliente: {order.customer.name}. '
            f'Seña: ${order.deposit_amount}.'
            + (f' MP pago #{mp_payment_id}.' if mp_payment_id else '')
        ),
        order=order,
    )
    _whatsapp_payment_received(tenant, order)
    _whatsapp_payment_confirmed_customer(tenant, order)
    n8n.send_order_event(
        tenant, order, n8n.PAYMENT_RECEIVED, MessageDelivery.PAYMENT_RECEIVED,
        payment={'mp_payment_id': str(mp_payment_id or '')},
    )


def notify_order_status(tenant, order, from_status, to_status, changed_by=None):
    actor = changed_by.get_full_name() or changed_by.username if changed_by else 'Sistema'
    _bulk_notify(
        tenant,
        Notification.ORDER_STATUS,
        f'Pedido #{order.pk} — {order.get_status_display()}',
        f'Estado actualizado por {actor}: {from_status} → {to_status}.',
        order=order,
    )
    n8n.send_order_event(
        tenant, order, n8n.ORDER_STATUS_CHANGED, STATUS_TEMPLATES.get(to_status),
        from_status=from_status, to_status=to_status,
    )


# ── WhatsApp ──────────────────────────────────────────────────────────────────

def send_whatsapp(tenant, phone, message, order=None):
    """
    Envía un mensaje WhatsApp y registra el intento en WhatsAppLog.
    Si WHATSAPP_PROVIDER_URL no está configurado, guarda el log con wa_link
    para que el admin pueda enviarlo manualmente desde el dashboard.
    """
    log = WhatsAppLog(tenant=tenant, phone=phone, message=message, order=order)

    provider_url = getattr(settings, 'WHATSAPP_PROVIDER_URL', '').strip()
    if not provider_url:
        log.save()
        return log

    try:
        import requests as req
        resp = req.post(
            provider_url,
            json={'phone': phone, 'message': message},
            timeout=10,
        )
        resp.raise_for_status()
        log.sent = True
        log.sent_at = timezone.now()
    except Exception as exc:
        log.error = str(exc)

    log.save()
    return log


def _get_admin_phone(tenant):
    try:
        p = tenant.profile
        return (p.whatsapp or p.phone).strip()
    except Exception:
        return ''


def _whatsapp_new_order(tenant, order):
    phone = _get_admin_phone(tenant)
    if not phone:
        return
    send_whatsapp(
        tenant=tenant,
        phone=phone,
        message=(
            f'Nuevo pedido #{order.pk} en {tenant.name}.\n'
            f'Cliente: {order.customer.name} ({order.customer.phone}).\n'
            f'Total: ${order.total} | Seña: ${order.deposit_amount}.\n'
            f'Fecha: {order.required_date.strftime("%d/%m/%Y")}.'
        ),
        order=order,
    )


def _whatsapp_payment_received(tenant, order):
    phone = _get_admin_phone(tenant)
    if not phone:
        return
    send_whatsapp(
        tenant=tenant,
        phone=phone,
        message=(
            f'Seña recibida para pedido #{order.pk} en {tenant.name}.\n'
            f'Cliente: {order.customer.name}.\n'
            f'Seña: ${order.deposit_amount}.'
        ),
        order=order,
    )


def _whatsapp_order_received_customer(tenant, order):
    phone = getattr(order.customer, 'phone', '').strip()
    if not phone:
        return
    date_str = order.required_date.strftime('%d/%m/%Y')
    send_whatsapp(
        tenant=tenant,
        phone=phone,
        message=(
            f'¡Hola {order.customer.name}! 🍪\n'
            f'Recibimos tu pedido #{order.pk} en {tenant.name}.\n'
            f'Total: ${order.total} | Seña: ${order.deposit_amount}.\n'
            f'Fecha solicitada: {date_str}.\n'
            f'En breve te contactamos para confirmar. ¡Gracias!'
        ),
        order=order,
    )


def _whatsapp_payment_confirmed_customer(tenant, order):
    phone = getattr(order.customer, 'phone', '').strip()
    if not phone:
        return
    date_str = order.required_date.strftime('%d/%m/%Y')
    send_whatsapp(
        tenant=tenant,
        phone=phone,
        message=(
            f'¡Hola {order.customer.name}! 🎉\n'
            f'Tu seña para el pedido #{order.pk} en {tenant.name} fue confirmada.\n'
            f'Nos pondremos en contacto para coordinar la entrega.\n'
            f'Fecha solicitada: {date_str}.\n'
            f'¡Gracias por elegirnos! 🐱'
        ),
        order=order,
    )

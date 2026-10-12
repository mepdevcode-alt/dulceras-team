"""
Servicio de emails transaccionales.
Usa HTML inline (compatible con todos los clientes de email).
Regla: nunca lanzar excepciones al caller — siempre silenciar y loggear.
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)


def _get_branding(tenant):
    try:
        p = tenant.profile
        return {
            'name': tenant.name,
            'primary': p.primary_color or '#3D1A0E',
            'accent': p.accent_color or '#E8889A',
            'bg': p.bg_color or '#FDF6EC',
        }
    except Exception:
        return {'name': tenant.name, 'primary': '#3D1A0E', 'accent': '#E8889A', 'bg': '#FDF6EC'}


def _html_wrapper(branding, title, body_html):
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:system-ui,-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <!-- Header -->
        <tr>
          <td style="background:{branding['primary']};padding:24px 32px;border-radius:12px 12px 0 0;text-align:center;">
            <p style="margin:0;color:white;font-size:22px;font-weight:700;">{branding['name']}</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="background:white;padding:32px;border-radius:0 0 12px 12px;">
            <h2 style="margin:0 0 20px;color:{branding['primary']};font-size:20px;">{title}</h2>
            {body_html}
            <hr style="border:none;border-top:1px solid #eee;margin:28px 0;">
            <p style="margin:0;color:#999;font-size:12px;text-align:center;">
              {branding['name']} · Cada pedido ayuda a gatitos 🐱
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _items_table(order):
    rows = ''.join(
        f'<tr>'
        f'<td style="padding:6px 0;color:#333;font-size:14px;">{item.quantity}x {item.product_name} — {item.variant_name}</td>'
        f'<td style="padding:6px 0;color:#333;font-size:14px;text-align:right;font-weight:600;">'
        f'${item.subtotal:,.0f}</td>'
        f'</tr>'
        for item in order.items.all()
    )
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:16px;">
      {rows}
    </table>"""


def _send(to_email, subject, text_body, html_body, from_email=None):
    """Devuelve True si el email se entregó al servidor SMTP."""
    if not to_email:
        return False
    try:
        from_addr = from_email or settings.DEFAULT_FROM_EMAIL
        msg = EmailMultiAlternatives(subject, text_body, from_addr, [to_email])
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
        return True
    except Exception as exc:
        logger.exception('Error sending email to %s: %s', to_email, exc)
        return False


def send_order_confirmation(tenant, order):
    """Email al cliente cuando se crea su pedido (pending_deposit)."""
    email = getattr(order.customer, 'email', '').strip()
    if not email:
        return False

    branding = _get_branding(tenant)
    date_str = order.required_date.strftime('%d/%m/%Y')
    items_html = _items_table(order)
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

    body_html = f"""
    <p style="color:#555;margin:0 0 16px;">¡Hola <strong>{order.customer.name}</strong>!
    Recibimos tu pedido. Acá va el resumen:</p>

    <div style="background:#f9f9f9;border-radius:8px;padding:16px;margin-bottom:20px;">
      <p style="margin:0 0 4px;color:#999;font-size:12px;text-transform:uppercase;letter-spacing:.5px;">Pedido #{order.pk}</p>
      <p style="margin:0 0 12px;color:#333;font-size:14px;">📅 Fecha solicitada: <strong>{date_str}</strong></p>
      {items_html}
      <table width="100%" style="border-top:1px solid #eee;padding-top:12px;margin-top:4px;">
        <tr><td style="color:#555;font-size:14px;">Subtotal</td>
            <td style="text-align:right;color:#333;font-size:14px;">${order.subtotal:,.0f}</td></tr>
        {'<tr><td style="color:#555;font-size:14px;">Envío</td><td style="text-align:right;color:#333;font-size:14px;">$' + f'{order.delivery_cost:,.0f}' + '</td></tr>' if order.delivery_cost else ''}
        <tr><td style="color:#333;font-size:15px;font-weight:700;padding-top:8px;">Total</td>
            <td style="text-align:right;color:#333;font-size:15px;font-weight:700;padding-top:8px;">${order.total:,.0f}</td></tr>
        <tr><td style="color:{branding['accent']};font-size:14px;padding-top:4px;">Seña ({int(order.deposit_percentage)}%)</td>
            <td style="text-align:right;color:{branding['accent']};font-size:14px;padding-top:4px;font-weight:600;">${order.deposit_amount:,.0f}</td></tr>
        <tr><td style="color:#555;font-size:14px;">Resto a pagar</td>
            <td style="text-align:right;color:#555;font-size:14px;">${order.balance_amount:,.0f}</td></tr>
      </table>
    </div>

    <p style="color:#555;font-size:14px;margin:0 0 20px;">
      Para confirmar tu pedido, necesitamos que abones la seña de
      <strong style="color:{branding['accent']};">${order.deposit_amount:,.0f}</strong>.
    </p>

    <div style="text-align:center;margin-bottom:24px;">
      <a href="{frontend_url}/pedido/{order.pk}"
         style="background:{branding['accent']};color:white;text-decoration:none;
                padding:14px 32px;border-radius:999px;font-weight:700;font-size:15px;display:inline-block;">
        Pagar seña →
      </a>
    </div>

    <p style="color:#999;font-size:13px;margin:0;">
      ¿Preguntas? Respondé este mail o escribinos por WhatsApp.
    </p>"""

    text_body = (
        f"Hola {order.customer.name}!\n\n"
        f"Recibimos tu pedido #{order.pk} en {tenant.name}.\n"
        f"Fecha solicitada: {date_str}\n"
        f"Total: ${order.total:,.0f}\n"
        f"Seña ({int(order.deposit_percentage)}%): ${order.deposit_amount:,.0f}\n\n"
        f"Pagá la seña en: {frontend_url}/pedido/{order.pk}\n\n"
        f"Gracias por elegirnos 🐱"
    )

    html_body = _html_wrapper(branding, f'Tu pedido #{order.pk} fue recibido', body_html)
    return _send(email, f'Recibimos tu pedido #{order.pk} — {tenant.name}', text_body, html_body)


def send_payment_confirmed(tenant, order):
    """Email al cliente cuando la seña es aprobada."""
    email = getattr(order.customer, 'email', '').strip()
    if not email:
        return False

    branding = _get_branding(tenant)
    date_str = order.required_date.strftime('%d/%m/%Y')

    body_html = f"""
    <p style="color:#555;margin:0 0 16px;">¡Hola <strong>{order.customer.name}</strong>! 🎉</p>

    <div style="background:{branding['bg']};border:2px solid {branding['accent']};
                border-radius:10px;padding:20px;text-align:center;margin-bottom:24px;">
      <p style="margin:0 0 4px;font-size:32px;">✅</p>
      <p style="margin:0;font-size:18px;font-weight:700;color:{branding['primary']};">
        Seña confirmada</p>
      <p style="margin:8px 0 0;color:{branding['accent']};font-size:20px;font-weight:700;">
        ${order.deposit_amount:,.0f}</p>
    </div>

    <div style="background:#f9f9f9;border-radius:8px;padding:16px;margin-bottom:20px;">
      <p style="margin:0 0 6px;color:#555;font-size:14px;">📦 Pedido #{order.pk}</p>
      <p style="margin:0 0 6px;color:#555;font-size:14px;">📅 Fecha solicitada: <strong>{date_str}</strong></p>
      <p style="margin:0;color:#555;font-size:14px;">
        Resto a pagar al recibir: <strong>${order.balance_amount:,.0f}</strong></p>
    </div>

    <p style="color:#555;font-size:14px;margin:0;">
      Estamos preparando tu pedido. Te vamos a avisar cuando esté listo. 🐱
    </p>"""

    text_body = (
        f"Hola {order.customer.name}!\n\n"
        f"Tu seña de ${order.deposit_amount:,.0f} para el pedido #{order.pk} fue confirmada.\n"
        f"Fecha solicitada: {date_str}\n"
        f"Resto a pagar: ${order.balance_amount:,.0f}\n\n"
        f"Estamos preparando tu pedido. Te avisamos cuando esté listo.\n\n"
        f"¡Gracias por elegirnos! 🐱"
    )

    html_body = _html_wrapper(branding, f'¡Seña confirmada! Pedido #{order.pk}', body_html)
    return _send(email, f'¡Seña confirmada! Pedido #{order.pk} — {tenant.name}', text_body, html_body)


def send_order_ready(tenant, order):
    """Email al cliente cuando el pedido está listo."""
    email = getattr(order.customer, 'email', '').strip()
    if not email:
        return False

    branding = _get_branding(tenant)
    is_delivery = order.delivery_method == 'delivery'

    try:
        address = tenant.profile.address or ''
    except Exception:
        address = ''

    body_html = f"""
    <p style="color:#555;margin:0 0 16px;">¡Hola <strong>{order.customer.name}</strong>! 🎉</p>

    <div style="background:{branding['bg']};border:2px solid {branding['primary']};
                border-radius:10px;padding:20px;text-align:center;margin-bottom:24px;">
      <p style="margin:0 0 4px;font-size:36px;">🎁</p>
      <p style="margin:0;font-size:18px;font-weight:700;color:{branding['primary']};">
        ¡Tu pedido está listo!</p>
    </div>

    <div style="background:#f9f9f9;border-radius:8px;padding:16px;margin-bottom:20px;">
      <p style="margin:0 0 6px;color:#555;font-size:14px;">📦 Pedido #{order.pk}</p>
      {'<p style="margin:0;color:#555;font-size:14px;">📍 Podés pasar a retirarlo en: <strong>' + address + '</strong></p>' if not is_delivery and address else ''}
      {'<p style="margin:0;color:#555;font-size:14px;">🚚 Estamos coordinando la entrega. Te contactamos en breve.</p>' if is_delivery else ''}
      <p style="margin:8px 0 0;color:#555;font-size:14px;">
        Resto a pagar: <strong>${order.balance_amount:,.0f}</strong></p>
    </div>

    <p style="color:#999;font-size:13px;margin:0;">
      ¡Gracias por elegirnos! Esperamos que lo disfrutes 🐱
    </p>"""

    text_body = (
        f"Hola {order.customer.name}!\n\n"
        f"¡Tu pedido #{order.pk} está listo!\n"
        f"{'Podés pasar a retirarlo en: ' + address if not is_delivery and address else 'Estamos coordinando la entrega.'}\n"
        f"Resto a pagar: ${order.balance_amount:,.0f}\n\n"
        f"¡Gracias por elegirnos! 🐱"
    )

    html_body = _html_wrapper(branding, f'Tu pedido #{order.pk} está listo 🎁', body_html)
    return _send(email, f'¡Tu pedido #{order.pk} está listo! — {tenant.name}', text_body, html_body)


def send_order_cancelled(tenant, order):
    """Email al cliente cuando el pedido es cancelado."""
    email = getattr(order.customer, 'email', '').strip()
    if not email:
        return False

    branding = _get_branding(tenant)

    body_html = f"""
    <p style="color:#555;margin:0 0 16px;">Hola <strong>{order.customer.name}</strong>,</p>
    <p style="color:#555;font-size:14px;margin:0 0 16px;">
      Tu pedido <strong>#{order.pk}</strong> fue cancelado.
    </p>
    <p style="color:#555;font-size:14px;margin:0;">
      Si tenés preguntas o querés coordinar la devolución de la seña,
      no dudes en contactarnos.
    </p>"""

    text_body = (
        f"Hola {order.customer.name},\n\n"
        f"Tu pedido #{order.pk} fue cancelado.\n"
        f"Si tenés preguntas, contactanos.\n\n{tenant.name}"
    )

    html_body = _html_wrapper(branding, f'Pedido #{order.pk} cancelado', body_html)
    return _send(email, f'Pedido #{order.pk} cancelado — {tenant.name}', text_body, html_body)


def send_custom_message(tenant, order, subject, message):
    """Email libre escrito por el admin desde el detalle del pedido."""
    email = getattr(order.customer, 'email', '').strip()
    if not email:
        return False

    branding = _get_branding(tenant)
    paragraphs = ''.join(
        f'<p style="color:#555;font-size:14px;line-height:1.6;margin:0 0 12px;">{escape(line)}</p>'
        for line in message.splitlines() if line.strip()
    )
    body_html = f"""
    <p style="color:#555;margin:0 0 16px;">¡Hola <strong>{escape(order.customer.name)}</strong>!</p>
    {paragraphs}
    <p style="color:#999;font-size:13px;margin:16px 0 0;">Pedido #{order.pk}</p>"""

    text_body = f"Hola {order.customer.name}!\n\n{message}\n\nPedido #{order.pk} — {tenant.name}"
    html_body = _html_wrapper(branding, escape(subject), body_html)
    return _send(email, f'{subject} — {tenant.name}', text_body, html_body)

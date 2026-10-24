"""
Capa de integración con Mercado Pago.
Aislada aquí para que las vistas no dependan del SDK directamente.
"""
from django.conf import settings

import mercadopago


def get_mp_sdk():
    """Retorna el SDK de MP o None si no hay token configurado."""
    token = getattr(settings, 'MERCADOPAGO_ACCESS_TOKEN', '')
    if not token:
        return None
    return mercadopago.SDK(token)


def build_mp_preference(payment_intent, frontend_url, notification_url):
    order = payment_intent.order
    pref = {
        "items": [
            {
                "title": f"Sena - Pedido #{order.id}",
                "quantity": 1,
                "unit_price": float(payment_intent.amount),
                "currency_id": "ARS",
            }
        ],
        "back_urls": {
            "success": f"{frontend_url}/payment/success/?order_id={order.id}",
            "failure": f"{frontend_url}/payment/failure/?order_id={order.id}",
            "pending": f"{frontend_url}/payment/pending/?order_id={order.id}",
        },
        "external_reference": str(order.id),
    }
    # Solo incluir notification_url si es una URL pública (no localhost)
    _local = ('localhost', '127.0.0.1', '0.0.0.0')
    if notification_url and not any(h in notification_url for h in _local):
        pref["notification_url"] = notification_url
    return pref

"""
Envía un pedido simulado al webhook de n8n para verificar la integración.
Uso: python manage.py test_n8n [--url http://127.0.0.1:5678/webhook/pedidos]
"""
import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


PAYLOAD = {
    "event": "order_created",
    "sent_at": "",
    "business": {
        "name": "Dulceras Team",
        "email": "dulcerasteam@gmail.com",
        "phone": "1122334455",
        "whatsapp": "1122334455",
        "instagram": "@dulcerasteam",
        "logo_url": "",
        "primary_color": "#9f4f67",
        "accent_color": "#E8889A",
        "bg_color": "#FDF6EC",
    },
    "order": {
        "id": 9999,
        "status": "pending_deposit",
        "status_display": "Esperando seña",
        "required_date": "2026-12-01",
        "required_date_display": "01/12/2026",
        "delivery_method": "pickup",
        "delivery_method_display": "Retiro en local",
        "delivery_address": None,
        "subtotal": 1800.0,
        "delivery_cost": 0.0,
        "discount_amount": 0.0,
        "coupon_code": "",
        "total": 1800.0,
        "deposit_percentage": 50.0,
        "deposit_amount": 900.0,
        "balance_amount": 900.0,
        "notes": "Sin gluten por favor",
        "url": "",
        "items": [
            {
                "product_name": "Torta Oreo",
                "variant_name": "Grande",
                "quantity": 1,
                "unit_price": 1800.0,
                "subtotal": 1800.0,
            }
        ],
    },
    "customer": {
        "name": "Cliente Prueba",
        "email": "prueba@ejemplo.com",
        "phone": "1155667788",
    },
    "delivery": {
        "id": 1,
        "template": "order_created",
        "recipient": "prueba@ejemplo.com",
        "subject": "Pedido confirmado #9999",
        "message": "",
        "callback_url": "",
    },
}


class Command(BaseCommand):
    help = "Envía un pedido simulado al webhook de n8n para verificar la integración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default="",
            help="URL del webhook de n8n (por defecto usa N8N_WEBHOOK_URL del .env).",
        )

    def handle(self, *args, **options):
        url = options["url"] or getattr(settings, "N8N_WEBHOOK_URL", "")
        if not url:
            self.stderr.write(self.style.ERROR(
                "No hay URL configurada. Usá --url o configurá N8N_WEBHOOK_URL en el .env."
            ))
            return

        payload = {**PAYLOAD, "sent_at": timezone.now().isoformat()}

        headers = {"Content-Type": "application/json"}
        secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
        header_name = getattr(settings, "N8N_WEBHOOK_SECRET_HEADER", "X-Webhook-Secret")
        if secret:
            headers[header_name] = secret

        self.stdout.write(f"Enviando pedido de prueba a {url} ...")
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            body = resp.text[:500].encode('ascii', errors='replace').decode('ascii')
            self.stdout.write(self.style.SUCCESS(
                f"Respuesta {resp.status_code}: {body}"
            ))
        except requests.ConnectionError:
            self.stderr.write(self.style.ERROR(
                f"No se pudo conectar a {url}. ¿Está corriendo n8n?"
            ))
        except requests.Timeout:
            self.stderr.write(self.style.ERROR("Timeout al conectar con n8n."))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Error inesperado: {exc}"))

"""
Crea un pedido de prueba y genera el link de pago de Mercado Pago.
Uso: python manage.py create_test_order
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from customers.models import Customer
from catalog.models import ProductVariant
from orders.models import Order, OrderItem
from payments.models import PaymentIntent
from payments.services import build_mp_preference, get_mp_sdk


class Command(BaseCommand):
    help = 'Crea un pedido de prueba y genera el link de pago sandbox de MP.'

    def handle(self, *args, **options):
        customer, _ = Customer.objects.get_or_create(
            email='comprador_prueba@test.com',
            defaults={'name': 'Comprador Prueba', 'phone': '1122334455'},
        )

        variant = (
            ProductVariant.objects
            .filter(is_active=True)
            .select_related('product')
            .first()
        )
        if not variant:
            raise CommandError('No hay variantes de producto activas. Corrí seed_dulceras primero.')

        required_date = datetime.date.today() + datetime.timedelta(days=14)

        order = Order.objects.create(
            customer=customer,
            status=Order.PENDING_DEPOSIT,
            required_date=required_date,
            delivery_method=Order.PICKUP,
            subtotal=variant.price,
            delivery_cost=0,
            discount_amount=0,
            deposit_percentage=50,
            notes='Pedido de prueba para test MP sandbox',
        )
        OrderItem.objects.create(
            order=order,
            product_variant=variant,
            product_name=variant.product.name,
            variant_name=variant.name,
            quantity=1,
            unit_price=variant.price,
            subtotal=variant.price,
        )

        self.stdout.write(f'Pedido #{order.pk} creado — {variant.product.name} ({variant.name}) — ${variant.price}')

        # Crear PaymentIntent por el monto de la seña
        deposit = order.subtotal * order.deposit_percentage / 100
        intent = PaymentIntent.objects.create(
            order=order,
            amount=deposit,
            status=PaymentIntent.PENDING,
        )

        # Generar preferencia de pago en MP
        notification_url = (
            getattr(settings, 'MP_WEBHOOK_URL', '')
            or 'http://localhost:8000/api/public/webhooks/mp/'
        )
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8000')
        try:
            sdk = get_mp_sdk()
            preference_data = build_mp_preference(
                payment_intent=intent,
                frontend_url=frontend_url,
                notification_url=notification_url,
            )
            result = sdk.preference().create(preference_data)
            pref = result.get('response', {})
            sandbox_url = pref.get('sandbox_init_point') or pref.get('init_point', '')
            if sandbox_url:
                self.stdout.write(self.style.SUCCESS('\nLink de pago SANDBOX:'))
                self.stdout.write(sandbox_url)
                self.stdout.write('\nAbri ese link en ventana INCOGNITO y paga con la cuenta compradora de prueba.')
            else:
                self.stderr.write(f'MP no devolvio URL. Respuesta: {result}')
        except Exception as exc:
            raise CommandError(f'Error al crear preferencia MP: {exc}')

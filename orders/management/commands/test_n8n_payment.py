"""
Simula un pago aprobado en un pedido y dispara el evento payment_received a n8n.
Uso: python manage.py test_n8n_payment --order 14
"""
from django.core.management.base import BaseCommand, CommandError
from orders.models import Order


class Command(BaseCommand):
    help = 'Simula un pago aprobado y dispara el evento payment_received a n8n.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order',
            type=int,
            default=None,
            help='ID del pedido (por defecto usa el último en estado pending_deposit).',
        )

    def handle(self, *args, **options):
        order_id = options['order']

        if order_id:
            try:
                order = Order.objects.select_related('customer').get(pk=order_id)
            except Order.DoesNotExist:
                raise CommandError(f'No existe el pedido #{order_id}.')
        else:
            order = (
                Order.objects
                .select_related('customer')
                .filter(status=Order.PENDING_DEPOSIT)
                .order_by('-created_at')
                .first()
            )
            if not order:
                raise CommandError('No hay pedidos en estado "Esperando seña". Pasá --order <id>.')

        self.stdout.write(f'Pedido #{order.pk} — {order.customer.name} — ${order.total}')
        self.stdout.write(f'Estado actual: {order.get_status_display()}')

        # Simular aprobación del pago
        from orders.models import OrderStatusHistory
        prev_status = order.status
        order.status = Order.DEPOSIT_PAID
        order.save(update_fields=['status', 'updated_at'])
        OrderStatusHistory.objects.create(
            order=order,
            from_status=prev_status,
            to_status=Order.DEPOSIT_PAID,
            changed_by=None,
            notes='Seña simulada via test_n8n_payment',
        )
        self.stdout.write(self.style.SUCCESS('Estado actualizado a: Seña pagada'))

        # Disparar notificación a n8n (modo síncrono para que el hilo no muera al salir)
        from django.conf import settings as django_settings
        original_async = getattr(django_settings, 'N8N_ASYNC', True)
        django_settings.N8N_ASYNC = False
        self.stdout.write('Enviando evento payment_received a n8n...')
        try:
            from notifications.services import notify_payment_received
            notify_payment_received(order, mp_payment_id='TEST-SIMULADO')
            self.stdout.write(self.style.SUCCESS('Evento enviado. Revisá Telegram y el email.'))
        except Exception as exc:
            raise CommandError(f'Error al notificar: {exc}')
        finally:
            django_settings.N8N_ASYNC = original_async

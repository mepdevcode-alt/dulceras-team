import datetime
from unittest import mock

import requests
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductVariant
from customers.models import Customer
from orders.models import Order, OrderItem
from tenants.models import Tenant
from users.models import User

from . import services
from .models import MessageDelivery

N8N_ON = dict(
    N8N_WEBHOOK_URL='http://127.0.0.1:5678/webhook/pedidos',
    N8N_WEBHOOK_SECRET='s3cret',
    N8N_ASYNC=False,
    N8N_CALLBACK_BASE_URL='http://127.0.0.1:8000',
)


class OrderFixtureMixin:
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Pastelería Test', slug='pasteleria-test')
        category = Category.objects.create(tenant=self.tenant, name='Tortas', slug='tortas')
        product = Product.objects.create(tenant=self.tenant, category=category, name='Torta')
        variant = ProductVariant.objects.create(
            tenant=self.tenant, product=product, name='Grande', price=1000,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, name='Ana', email='ana@example.com',
        )
        self.order = Order.objects.create(
            tenant=self.tenant, customer=self.customer, status=Order.PENDING_DEPOSIT,
            required_date=datetime.date(2026, 12, 1),
            subtotal=2000, total=2000, deposit_amount=1000, balance_amount=1000,
        )
        OrderItem.objects.create(
            order=self.order, product_variant=variant, product_name='Torta',
            variant_name='Grande', unit_price=1000, quantity=2, subtotal=2000,
        )

    def last_delivery(self):
        return MessageDelivery.objects.latest('created_at')


class AutomaticEventsTests(OrderFixtureMixin, TestCase):
    def _notify_new_order(self):
        with self.captureOnCommitCallbacks(execute=True):
            services.notify_new_order(self.tenant, self.order)

    @override_settings(N8N_WEBHOOK_URL='')
    @mock.patch('notifications.n8n.requests.post')
    def test_disabled_uses_django_email_and_logs_it(self, post):
        self._notify_new_order()
        post.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)
        d = self.last_delivery()
        self.assertEqual((d.status, d.provider), (MessageDelivery.SENT, MessageDelivery.PROVIDER_DJANGO))

    @override_settings(**N8N_ON)
    @mock.patch('notifications.n8n.requests.post')
    def test_enabled_sends_event_and_queues_delivery(self, post):
        self._notify_new_order()

        post.assert_called_once()
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers'], {'X-Webhook-Secret': 's3cret'})
        payload = kwargs['json']
        d = self.last_delivery()
        self.assertEqual(payload['event'], 'order_created')
        self.assertEqual(payload['tenant']['name'], 'Pastelería Test')
        self.assertEqual(payload['order']['items'][0]['quantity'], 2)
        self.assertEqual(payload['delivery']['id'], d.pk)
        self.assertEqual(payload['delivery']['template'], MessageDelivery.ORDER_CREATED)
        self.assertEqual(
            payload['delivery']['callback_url'],
            f'http://127.0.0.1:8000/api/n8n/deliveries/{d.pk}/status/',
        )
        self.assertEqual(d.status, MessageDelivery.QUEUED)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**N8N_ON)
    @mock.patch('notifications.n8n.requests.post', side_effect=requests.ConnectionError('down'))
    def test_n8n_down_falls_back_to_django_email(self, post):
        self._notify_new_order()
        self.assertEqual(len(mail.outbox), 1)
        d = self.last_delivery()
        self.assertEqual((d.status, d.provider), (MessageDelivery.SENT, MessageDelivery.PROVIDER_DJANGO))
        self.assertIn('n8n no disponible', d.error)

    @override_settings(**N8N_ON)
    @mock.patch('notifications.n8n.requests.post')
    def test_customer_without_email_is_skipped_but_event_still_sent(self, post):
        self.customer.email = ''
        self.customer.save()
        self._notify_new_order()
        self.assertIsNone(post.call_args.kwargs['json']['delivery'])
        self.assertEqual(self.last_delivery().status, MessageDelivery.SKIPPED)

    @override_settings(**N8N_ON)
    @mock.patch('notifications.n8n.requests.post')
    def test_payment_received_includes_payment_id(self, post):
        with self.captureOnCommitCallbacks(execute=True):
            services.notify_payment_received(self.tenant, self.order, mp_payment_id='123')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['event'], 'payment_received')
        self.assertEqual(payload['payment'], {'mp_payment_id': '123'})

    @override_settings(**N8N_ON)
    @mock.patch('notifications.n8n.requests.post', side_effect=requests.ConnectionError)
    def test_status_without_email_creates_no_delivery(self, post):
        with self.captureOnCommitCallbacks(execute=True):
            services.notify_order_status(
                self.tenant, self.order, Order.DEPOSIT_PAID, Order.IN_PRODUCTION,
            )
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['to_status'], Order.IN_PRODUCTION)
        self.assertIsNone(payload['delivery'])
        self.assertFalse(MessageDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(N8N_WEBHOOK_URL='')
    @mock.patch('notifications.n8n.requests.post')
    def test_status_without_email_and_n8n_off_does_nothing(self, post):
        with self.captureOnCommitCallbacks(execute=True):
            services.notify_order_status(
                self.tenant, self.order, Order.DEPOSIT_PAID, Order.IN_PRODUCTION,
            )
        post.assert_not_called()
        self.assertFalse(MessageDelivery.objects.exists())


@override_settings(**N8N_ON)
class CallbackTests(OrderFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.delivery = MessageDelivery.objects.create(
            tenant=self.tenant, order=self.order, template=MessageDelivery.ORDER_CREATED,
            recipient='ana@example.com', status=MessageDelivery.QUEUED,
        )
        self.url = f'/api/n8n/deliveries/{self.delivery.pk}/status/'
        self.client = APIClient()

    def test_rejects_wrong_secret(self):
        res = self.client.post(self.url, {'status': 'sent'}, format='json',
                               HTTP_X_WEBHOOK_SECRET='nope')
        self.assertEqual(res.status_code, 403)

    def test_marks_sent(self):
        res = self.client.post(self.url, {'status': 'sent'}, format='json',
                               HTTP_X_WEBHOOK_SECRET='s3cret')
        self.assertEqual(res.status_code, 200)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, MessageDelivery.SENT)
        self.assertIsNotNone(self.delivery.sent_at)

    def test_marks_failed_with_error(self):
        self.client.post(self.url, {'status': 'failed', 'error': 'SMTP 535'}, format='json',
                         HTTP_X_WEBHOOK_SECRET='s3cret')
        self.delivery.refresh_from_db()
        self.assertEqual((self.delivery.status, self.delivery.error), (MessageDelivery.FAILED, 'SMTP 535'))

    def test_does_not_overwrite_final_status(self):
        self.delivery.status = MessageDelivery.SENT
        self.delivery.save()
        res = self.client.post(self.url, {'status': 'failed'}, format='json',
                               HTTP_X_WEBHOOK_SECRET='s3cret')
        self.assertFalse(res.json()['updated'])
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, MessageDelivery.SENT)


@override_settings(**N8N_ON)
@mock.patch('notifications.n8n.requests.post')
class AdminMessagesApiTests(OrderFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='admin-test', password='x', tenant=self.tenant, role=User.TENANT_ADMIN,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = f'/api/admin/orders/{self.order.pk}/messages/'

    def _post(self, data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data, format='json')

    def test_send_custom_message(self, post):
        res = self._post({'template': 'custom', 'subject': 'Hola', 'message': 'Tu torta va en camino'})
        self.assertEqual(res.status_code, 201, res.content)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['event'], 'message_requested')
        self.assertEqual(payload['delivery']['subject'], 'Hola')
        self.assertEqual(payload['delivery']['message'], 'Tu torta va en camino')
        d = self.last_delivery()
        self.assertEqual(d.triggered_by, self.admin)

    def test_custom_requires_subject_and_message(self, post):
        res = self._post({'template': 'custom', 'subject': '', 'message': ''})
        self.assertEqual(res.status_code, 400)
        post.assert_not_called()

    def test_template_not_allowed_for_status(self, post):
        res = self._post({'template': 'order_ready'})
        self.assertEqual(res.status_code, 400)
        post.assert_not_called()

    def test_resend_copies_original(self, post):
        original = MessageDelivery.objects.create(
            tenant=self.tenant, order=self.order, template=MessageDelivery.CUSTOM,
            subject='Asunto', message='Texto', recipient='ana@example.com',
            status=MessageDelivery.FAILED,
        )
        res = self._post({'resend_of': original.pk})
        self.assertEqual(res.status_code, 201, res.content)
        d = self.last_delivery()
        self.assertEqual((d.template, d.subject, d.resent_from), (MessageDelivery.CUSTOM, 'Asunto', original))

    def test_list_messages(self, post):
        self._post({'template': 'order_created'})
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0]['template'], 'order_created')
        self.assertEqual(res.json()[0]['triggered_by_name'], 'admin-test')

    def test_other_tenant_cannot_access(self, post):
        other = Tenant.objects.create(name='Otro', slug='otro')
        user = User.objects.create_user(username='otro', password='x', tenant=other,
                                        role=User.TENANT_ADMIN)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_customer_role_forbidden(self, post):
        user = User.objects.create_user(username='cli', password='x', tenant=self.tenant,
                                        role=User.CUSTOMER)
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

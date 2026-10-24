"""
Tests de seguridad: autenticación, acceso por rol y throttling.
Correr con: python manage.py test tests.test_security
"""
import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.models import Order
from customers.models import Customer

User = get_user_model()


def make_user(username, role=User.ADMIN):
    return User.objects.create_user(
        username=username,
        password='testpass123',
        role=role,
    )


def jwt_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


def make_order(email='c@test.com'):
    import datetime
    customer, _ = Customer.objects.get_or_create(
        email=email, defaults={'name': 'Cliente Test'},
    )
    return Order.objects.create(
        customer=customer,
        status=Order.PENDING_DEPOSIT,
        required_date=datetime.date.today(),
        delivery_method=Order.PICKUP,
        subtotal=100,
        deposit_percentage=50,
    )


# ── 1. Autenticación requerida ────────────────────────────────────────────────

class AuthRequiredTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_orders_list_requires_auth(self):
        resp = self.client.get('/api/admin/orders/')
        self.assertIn(resp.status_code, (401, 403))

    def test_catalog_admin_requires_auth(self):
        resp = self.client.get('/api/admin/catalog/products/')
        self.assertIn(resp.status_code, (401, 403))

    def test_settings_requires_auth(self):
        resp = self.client.get('/api/admin/settings/')
        self.assertIn(resp.status_code, (401, 403))

    def test_superadmin_requires_auth(self):
        resp = self.client.get('/api/superadmin/webhooks/')
        self.assertIn(resp.status_code, (401, 403))

    def test_superadmin_requires_superadmin_role(self):
        client = jwt_client(make_user('regularadmin', User.ADMIN))
        resp = client.get('/api/superadmin/webhooks/')
        self.assertIn(resp.status_code, (401, 403))


# ── 2. Un cliente logueado no accede al panel admin ──────────────────────────

class CustomerCannotAccessAdminTest(TestCase):
    def setUp(self):
        self.order = make_order()
        self.customer_client = jwt_client(make_user('cliente', User.CUSTOMER))
        self.admin_client = jwt_client(make_user('admin'))

    def test_customer_cannot_list_orders(self):
        resp = self.customer_client.get('/api/admin/orders/')
        self.assertEqual(resp.status_code, 403)

    def test_customer_cannot_see_order(self):
        resp = self.customer_client.get(f'/api/admin/orders/{self.order.pk}/')
        self.assertEqual(resp.status_code, 403)

    def test_customer_cannot_patch_order(self):
        resp = self.customer_client.patch(
            f'/api/admin/orders/{self.order.pk}/',
            {'notes': 'hack'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_list_orders(self):
        resp = self.admin_client.get('/api/admin/orders/')
        self.assertEqual(resp.status_code, 200)


# ── 3. Validación de entrada (400 en payloads inválidos) ─────────────────────

class InputValidationTest(TestCase):
    def test_login_wrong_credentials_returns_401(self):
        resp = self.client.post(
            '/api/token/',
            {'username': 'nobody', 'password': 'wrong'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_login_empty_body_returns_400(self):
        resp = self.client.post('/api/token/', {}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)


# ── 4. Rate limiting — verificar que los throttles están configurados ─────────

class ThrottleConfigTest(TestCase):
    """
    Verifica que los throttles están aplicados en las vistas críticas.
    Tests de integración reales del 429 requieren un entorno con cache Redis/Memcached
    y control de headers; aquí verificamos la configuración de las clases.
    """

    def test_login_view_has_throttle(self):
        from users.views import CustomTokenObtainPairView, LoginRateThrottle
        self.assertIn(LoginRateThrottle, CustomTokenObtainPairView.throttle_classes)

    def test_login_throttle_scope(self):
        from users.views import LoginRateThrottle
        self.assertEqual(LoginRateThrottle.scope, 'login')

    def test_webhook_view_has_throttle(self):
        from payments.views import MercadoPagoWebhookView, WebhookRateThrottle
        self.assertIn(WebhookRateThrottle, MercadoPagoWebhookView.throttle_classes)

    def test_webhook_throttle_scope(self):
        from payments.views import WebhookRateThrottle
        self.assertEqual(WebhookRateThrottle.scope, 'webhook')

    def test_throttle_rates_configured(self):
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('login', rates)
        self.assertIn('webhook', rates)


# ── 5. Sin fuga de datos sensibles ───────────────────────────────────────────

class NoDataLeakTest(TestCase):
    def setUp(self):
        make_order()
        self.client = jwt_client(make_user('leak_admin'))

    def test_user_response_has_no_password(self):
        resp = self.client.get('/api/admin/orders/')
        self.assertEqual(resp.status_code, 200)
        text = json.dumps(resp.json())
        self.assertNotIn('password', text)
        self.assertNotIn('pbkdf2_sha', text)

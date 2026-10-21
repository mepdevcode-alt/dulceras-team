"""
Tests de seguridad: aislamiento multi-tenant, autenticación y throttling.
Correr con: python manage.py test tests.test_security
"""
import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tenants.models import Tenant, Plan
from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem
from customers.models import Customer

User = get_user_model()


def make_tenant(slug, name=None):
    return Tenant.objects.create(slug=slug, name=name or slug, is_active=True)


def make_admin(tenant, username):
    return User.objects.create_user(
        username=username,
        password='testpass123',
        tenant=tenant,
        role=User.TENANT_ADMIN,
    )


def jwt_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


def make_order(tenant, customer=None):
    import datetime
    if customer is None:
        customer, _ = Customer.objects.get_or_create(
            tenant=tenant, email=f'c@{tenant.slug}.com',
            defaults={'name': f'Cliente {tenant.slug}'},
        )
    return Order.objects.create(
        tenant=tenant,
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
        self.tenant = make_tenant('auth-test')
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
        resp = self.client.get('/api/superadmin/tenants/')
        self.assertIn(resp.status_code, (401, 403))

    def test_superadmin_requires_platform_owner(self):
        tenant = make_tenant('regular-tenant')
        admin = make_admin(tenant, 'regularadmin')
        client = jwt_client(admin)
        resp = client.get('/api/superadmin/tenants/')
        self.assertIn(resp.status_code, (401, 403))


# ── 2. Aislamiento multi-tenant ───────────────────────────────────────────────

class TenantIsolationTest(TestCase):
    def setUp(self):
        self.tenant_a = make_tenant('tenant-a')
        self.tenant_b = make_tenant('tenant-b')
        self.admin_a = make_admin(self.tenant_a, 'admin_a')
        self.admin_b = make_admin(self.tenant_b, 'admin_b')
        self.order_a = make_order(self.tenant_a)
        self.order_b = make_order(self.tenant_b)
        self.client_a = jwt_client(self.admin_a)
        self.client_b = jwt_client(self.admin_b)

    def test_admin_a_cannot_see_order_b(self):
        resp = self.client_a.get(f'/api/admin/orders/{self.order_b.pk}/')
        self.assertIn(resp.status_code, (403, 404))

    def test_admin_b_cannot_see_order_a(self):
        resp = self.client_b.get(f'/api/admin/orders/{self.order_a.pk}/')
        self.assertIn(resp.status_code, (403, 404))

    def test_orders_list_only_own_tenant(self):
        resp = self.client_a.get('/api/admin/orders/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        ids = [r['id'] for r in results]
        self.assertIn(self.order_a.pk, ids)
        self.assertNotIn(self.order_b.pk, ids)

    def test_admin_a_cannot_patch_order_b(self):
        resp = self.client_a.patch(
            f'/api/admin/orders/{self.order_b.pk}/',
            {'notes': 'hack'},
            format='json',
        )
        self.assertIn(resp.status_code, (403, 404, 405))


# ── 3. Validación de entrada (400 en payloads inválidos) ─────────────────────

class InputValidationTest(TestCase):
    def test_register_missing_fields_returns_400(self):
        resp = self.client.post(
            '/api/register/',
            {'name': 'Test'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_slug_returns_400(self):
        make_tenant('existing-slug')
        payload = {
            'name': 'Test', 'slug': 'existing-slug',
            'admin_username': 'user1', 'admin_password': 'pass1234',
        }
        resp = self.client.post('/api/register/', payload, content_type='application/json')
        self.assertEqual(resp.status_code, 400)

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

    def test_register_view_has_throttle(self):
        from tenants.views import RegisterView, RegisterRateThrottle
        self.assertIn(RegisterRateThrottle, RegisterView.throttle_classes)

    def test_register_throttle_scope(self):
        from tenants.views import RegisterRateThrottle
        self.assertEqual(RegisterRateThrottle.scope, 'register')

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
        self.assertIn('register', rates)
        self.assertIn('webhook', rates)


# ── 5. Sin fuga de datos sensibles ───────────────────────────────────────────

class NoDataLeakTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant('leak-test')
        self.admin = make_admin(self.tenant, 'leak_admin')
        self.client = jwt_client(self.admin)

    def test_user_response_has_no_password(self):
        resp = self.client.get('/api/admin/orders/')
        self.assertEqual(resp.status_code, 200)
        text = json.dumps(resp.json())
        self.assertNotIn('password', text)
        self.assertNotIn('pbkdf2_sha', text)

from django.test import TestCase
from rest_framework.test import APIClient

from customers.models import Customer
from tenants.models import Tenant
from users.models import User

# Endpoints del panel admin: un cliente logueado no debe poder usarlos
ADMIN_ENDPOINTS = [
    '/api/admin/orders/',
    '/api/admin/orders/stats/',
    '/api/admin/customers/',
    '/api/admin/reviews/',
    '/api/admin/coupons/',
    '/api/admin/catalog/products/',
    '/api/admin/catalog/categories/',
    '/api/admin/payments/',
    '/api/admin/notifications/',
    '/api/admin/settings/',
    '/api/admin/delivery-zones/',
]


class TeamAccessTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Pastelería Test', slug='pasteleria-test')
        self.admin = User.objects.create_user(
            username='admin-test', password='pass-123', tenant=self.tenant, role=User.TENANT_ADMIN,
        )
        self.customer_user = User.objects.create_user(
            username='cliente@example.com', password='pass-123', tenant=self.tenant, role=User.CUSTOMER,
        )
        Customer.objects.create(
            tenant=self.tenant, user=self.customer_user, name='Cliente', email='cliente@example.com',
        )
        self.client = APIClient()

    def test_panel_login_rejects_customer(self):
        res = self.client.post('/api/token/', {'username': 'cliente@example.com', 'password': 'pass-123'},
                               format='json')
        self.assertEqual(res.status_code, 403)
        self.assertIn('cliente', res.json()['detail'])
        self.assertNotIn('access', res.json())

    def test_panel_login_accepts_team_member(self):
        res = self.client.post('/api/token/', {'username': 'admin-test', 'password': 'pass-123'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.json())

    def test_panel_login_wrong_password_is_still_401(self):
        res = self.client.post('/api/token/', {'username': 'cliente@example.com', 'password': 'mal'},
                               format='json')
        self.assertEqual(res.status_code, 401)

    def test_customer_cannot_use_admin_api(self):
        self.client.force_authenticate(self.customer_user)
        for url in ADMIN_ENDPOINTS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_customer_cannot_change_order_status(self):
        self.client.force_authenticate(self.customer_user)
        res = self.client.patch('/api/admin/orders/1/status/', {'status': 'cancelled'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_team_member_can_use_admin_api(self):
        self.client.force_authenticate(self.admin)
        for url in ADMIN_ENDPOINTS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_customer_account_api_still_works(self):
        self.client.force_authenticate(self.customer_user)
        res = self.client.get(f'/api/public/{self.tenant.slug}/customers/me/')
        self.assertEqual(res.status_code, 200)

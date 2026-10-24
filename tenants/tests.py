from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductVariant
from tenants.models import BusinessProfile, DeliveryZone
from users.models import User


class SingleBusinessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin-test', password='x', role=User.ADMIN)
        self.superadmin = User.objects.create_user(username='super-test', password='x', role=User.SUPERADMIN)

    def test_load_returns_existing_row_even_if_pk_is_not_1(self):
        BusinessProfile.objects.create(pk=7, name='Migrado')
        self.assertEqual(BusinessProfile.load().name, 'Migrado')
        self.assertEqual(BusinessProfile.objects.count(), 1)

    def test_load_creates_row_when_empty(self):
        self.assertEqual(BusinessProfile.load().deposit_percentage, Decimal('50'))
        self.assertEqual(BusinessProfile.objects.count(), 1)

    def test_admin_settings_get_and_patch(self):
        BusinessProfile.objects.create(name='Dulceras Team')
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/admin/settings/').json()['name'], 'Dulceras Team')
        res = self.client.patch('/api/admin/settings/', {'name': 'Nuevo nombre', 'deposit_percentage': '40'},
                                format='json')
        self.assertEqual(res.status_code, 200, res.content)
        profile = BusinessProfile.load()
        self.assertEqual((profile.name, profile.deposit_percentage), ('Nuevo nombre', Decimal('40')))

    def test_public_endpoints_without_slug(self):
        BusinessProfile.objects.create(name='Dulceras Team')
        DeliveryZone.objects.create(name='Almagro', price=0)
        category = Category.objects.create(name='Tortas', slug='tortas')
        product = Product.objects.create(category=category, name='Torta')
        ProductVariant.objects.create(product=product, name='Grande', price=1000)
        self.assertEqual(self.client.get('/api/public/branding/').json()['business_name'], 'Dulceras Team')
        self.assertEqual(len(self.client.get('/api/public/delivery-zones/').json()), 1)
        self.assertEqual(self.client.get('/api/public/products/').json()['count'], 1)
        self.assertEqual(self.client.get('/api/public/calendar/availability/').status_code, 200)
        res = self.client.post('/api/public/coupons/validate/', {'code': 'NOEXISTE', 'subtotal': 100}, format='json')
        self.assertEqual(res.json()['valid'], False)

    def test_mp_webhook_new_and_legacy_url(self):
        # La URL con slug la siguen usando preferencias de pago creadas antes del cambio
        for url in ('/api/public/webhooks/mp/', '/api/public/dulceras-team/webhooks/mp/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_system_panel_only_for_superadmin(self):
        for url in ('/api/superadmin/webhooks/', '/api/superadmin/deliveries/', '/api/superadmin/audit/'):
            with self.subTest(url=url):
                self.client.force_authenticate(self.admin)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.client.force_authenticate(self.superadmin)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_superadmin_can_use_admin_panel(self):
        self.client.force_authenticate(self.superadmin)
        self.assertEqual(self.client.get('/api/admin/orders/').status_code, 200)

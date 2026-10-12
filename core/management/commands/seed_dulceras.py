from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from django.utils import timezone
from datetime import timedelta
from tenants.models import Plan, Subscription, Tenant, BusinessProfile, DeliveryZone
from catalog.models import Category, Product, ProductVariant
from customers.models import Customer, CustomerAddress
from orders.models import Order, OrderItem, OrderStatusHistory

User = get_user_model()


TENANT_SLUG = 'dulceras-team'

CATEGORIES = [
    {'name': 'Cookies estilo NY',   'slug': 'cookies-ny',         'description': 'Cookies gigantes con chips de chocolate, estilo Nueva York.'},
    {'name': 'Budines',             'slug': 'budines',             'description': 'Budines húmedos y esponjosos en distintos sabores.'},
    {'name': 'Tortas enteras',      'slug': 'tortas',              'description': 'Tortas completas para celebrar o darte un gusto enorme.'},
    {'name': 'Postres bajoneros',   'slug': 'postres-bajoneros',   'description': 'Postres cremosos para los momentos que piden algo especial.'},
    {'name': 'Brownie Box',         'slug': 'brownie-box',         'description': 'Brownies fudgy, densos y con costra crujiente.'},
    {'name': 'Chipá',               'slug': 'chipa',               'description': 'Chipá esponjoso, recién horneado, perfecto para cualquier hora.'},
]

PRODUCTS = [
    {
        'category_slug': 'cookies-ny',
        'name': 'Cookie Chocolate Chips',
        'description': 'Cookie enorme estilo NY con chips de chocolate belga. Crocante por fuera, suave y melosa por dentro.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Unidad',   'price': Decimal('850')},
            {'name': 'Caja x4', 'price': Decimal('3000')},
            {'name': 'Caja x6', 'price': Decimal('4300')},
        ],
    },
    {
        'category_slug': 'cookies-ny',
        'name': 'Cookie Doble Chocolate',
        'description': 'Masa de cacao con chips de chocolate blanco y negro. Intensidad pura.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Unidad',   'price': Decimal('900')},
            {'name': 'Caja x4', 'price': Decimal('3200')},
            {'name': 'Caja x6', 'price': Decimal('4600')},
        ],
    },
    {
        'category_slug': 'budines',
        'name': 'Budín de Limón',
        'description': 'Budín húmedo con glaseado de limón. Fresco, liviano y adictivo.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Pequeño (6 porciones)',  'price': Decimal('3800')},
            {'name': 'Grande (12 porciones)', 'price': Decimal('6500')},
        ],
    },
    {
        'category_slug': 'budines',
        'name': 'Budín de Banana y Nuez',
        'description': 'El clásico reconfortante con banana madura, nueces tostadas y canela.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Pequeño (6 porciones)',  'price': Decimal('4000')},
            {'name': 'Grande (12 porciones)', 'price': Decimal('7000')},
        ],
    },
    {
        'category_slug': 'tortas',
        'name': 'Torta de Chocolate',
        'description': 'Torta húmeda de chocolate con ganache y decoración artesanal. El postre que todos piden.',
        'requires_advance_hours': 72,
        'variants': [
            {'name': '1/4 (4-6 porciones)',    'price': Decimal('9000')},
            {'name': '1/2 (8-10 porciones)',   'price': Decimal('16000')},
            {'name': 'Entera (16-20 porciones)', 'price': Decimal('28000')},
        ],
    },
    {
        'category_slug': 'tortas',
        'name': 'Torta de Vainilla y Frutos Rojos',
        'description': 'Bizcochuelo de vainilla con crema y coulis de frutos rojos frescos.',
        'requires_advance_hours': 72,
        'variants': [
            {'name': '1/4 (4-6 porciones)',    'price': Decimal('9500')},
            {'name': '1/2 (8-10 porciones)',   'price': Decimal('17000')},
            {'name': 'Entera (16-20 porciones)', 'price': Decimal('30000')},
        ],
    },
    {
        'category_slug': 'postres-bajoneros',
        'name': 'Cheesecake de Dulce de Leche',
        'description': 'Base de galletitas, relleno cremoso y cobertura de dulce de leche repostero.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Porción individual', 'price': Decimal('1400')},
            {'name': 'Caja x4 porciones', 'price': Decimal('5200')},
        ],
    },
    {
        'category_slug': 'postres-bajoneros',
        'name': 'Tiramisú',
        'description': 'El clásico italiano con mascarpone, café y cacao amargo. Suave y reconfortante.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Porción individual', 'price': Decimal('1500')},
            {'name': 'Caja x4 porciones', 'price': Decimal('5500')},
        ],
    },
    {
        'category_slug': 'brownie-box',
        'name': 'Brownie Clásico',
        'description': 'Brownie fudgy de chocolate amargo con costra crujiente. El favorito de todos.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Caja x4', 'price': Decimal('3400')},
            {'name': 'Caja x6', 'price': Decimal('4800')},
        ],
    },
    {
        'category_slug': 'brownie-box',
        'name': 'Brownie con Chips de Chocolate Blanco',
        'description': 'Brownie de chocolate negro con chips de chocolate blanco. Dulce y con contraste.',
        'requires_advance_hours': 48,
        'variants': [
            {'name': 'Caja x4', 'price': Decimal('3600')},
            {'name': 'Caja x6', 'price': Decimal('5100')},
        ],
    },
    {
        'category_slug': 'chipa',
        'name': 'Chipá Tradicional',
        'description': 'Chipá esponjoso con queso, recién horneado. Crujiente por fuera y tierno por dentro.',
        'requires_advance_hours': 24,
        'variants': [
            {'name': 'Unidad',    'price': Decimal('450')},
            {'name': 'Bolsa x6', 'price': Decimal('2400')},
            {'name': 'Bolsa x12','price': Decimal('4500')},
        ],
    },
]

DELIVERY_ZONES = [
    {'name': 'Almagro',           'description': 'Envío gratuito en Almagro',            'price': Decimal('0')},
    {'name': 'CABA — Centro',     'description': 'Palermo, Recoleta, San Telmo y alrededores', 'price': Decimal('1500')},
    {'name': 'CABA — Norte',      'description': 'Belgrano, Núñez, Colegiales y alrededores',  'price': Decimal('1500')},
    {'name': 'CABA — Sur',        'description': 'Boedo, Caballito, Flores y alrededores',      'price': Decimal('1500')},
    {'name': 'CABA — Oeste',      'description': 'Villa del Parque, Devoto y alrededores',      'price': Decimal('1800')},
    {'name': 'GBA — Zona Norte',  'description': 'San Isidro, Vicente López y alrededores',     'price': Decimal('2800')},
    {'name': 'GBA — Zona Oeste',  'description': 'Morón, Ramos Mejía y alrededores',            'price': Decimal('2800')},
]

# ── Pedidos de demo ──────────────────────────────────────────────────────────
# Emails @example.com: nunca le llegan a una persona real al probar n8n/SMTP.
DEMO_ORDER_MARKER = 'seed-demo'

DEMO_CUSTOMERS = [
    {'name': 'Lucía Fernández',  'phone': '1145551001', 'email': 'lucia.fernandez@example.com',
     'address': {'street': 'Av. Corrientes 4120, 3°B', 'neighborhood': 'Almagro'}},
    {'name': 'Martín Gómez',     'phone': '1145551002', 'email': 'martin.gomez@example.com',
     'address': {'street': 'Gorriti 5230', 'neighborhood': 'Palermo'}},
    {'name': 'Sofía Ramírez',    'phone': '1145551003', 'email': 'sofia.ramirez@example.com',
     'address': {'street': 'Cabildo 2450, 7°A', 'neighborhood': 'Belgrano'}},
    {'name': 'Julián Pereyra',   'phone': '1145551004', 'email': 'julian.pereyra@example.com',
     'address': {'street': 'Av. La Plata 1380', 'neighborhood': 'Boedo'}},
    {'name': 'Camila Torres',    'phone': '1145551005', 'email': 'camila.torres@example.com',
     'address': {'street': 'Av. del Libertador 15200', 'neighborhood': 'Acassuso', 'city': 'San Isidro'}},
    {'name': 'Tomás Álvarez',    'phone': '1145551006', 'email': 'tomas.alvarez@example.com', 'address': None},
    {'name': 'Valentina Sosa',   'phone': '1145551007', 'email': 'valentina.sosa@example.com', 'address': None},
    {'name': 'Nicolás Díaz',     'phone': '1145551008', 'email': '', 'address': None},  # sin email: prueba "Sin destinatario"
]

# days: fecha de entrega relativa a hoy; created: hace cuántos días se hizo el pedido;
# zone: None = retiro en local; items: (producto, variante, cantidad)
DEMO_ORDERS = [
    {'customer': 0, 'status': 'delivered', 'days': -20, 'created': 24, 'zone': None,
     'items': [('Torta de Chocolate', 'Entera (16-20 porciones)', 1)],
     'notes': 'Para un cumpleaños de 15, sin decoración con nombre.'},
    {'customer': 1, 'status': 'delivered', 'days': -12, 'created': 15, 'zone': 'CABA — Centro',
     'items': [('Cookie Chocolate Chips', 'Caja x6', 2), ('Brownie Clásico', 'Caja x4', 1)], 'notes': ''},
    {'customer': 2, 'status': 'delivered', 'days': -5, 'created': 8, 'zone': None,
     'items': [('Budín de Limón', 'Grande (12 porciones)', 1), ('Chipá Tradicional', 'Bolsa x12', 1)], 'notes': ''},
    {'customer': 3, 'status': 'cancelled', 'days': -3, 'created': 6, 'zone': None,
     'items': [('Tiramisú', 'Caja x4 porciones', 1)], 'notes': 'El cliente canceló por viaje.'},
    {'customer': 0, 'status': 'out_for_delivery', 'days': 0, 'created': 3, 'zone': 'Almagro',
     'items': [('Cheesecake de Dulce de Leche', 'Caja x4 porciones', 1)], 'notes': 'Tocar timbre 3°B.'},
    {'customer': 5, 'status': 'ready', 'days': 0, 'created': 2, 'zone': None,
     'items': [('Chipá Tradicional', 'Bolsa x6', 2)], 'notes': ''},
    {'customer': 2, 'status': 'in_production', 'days': 1, 'created': 4, 'zone': 'CABA — Norte',
     'items': [('Torta de Vainilla y Frutos Rojos', '1/2 (8-10 porciones)', 1)], 'notes': 'Sin frutillas, solo arándanos.'},
    {'customer': 6, 'status': 'in_production', 'days': 2, 'created': 3, 'zone': None,
     'items': [('Cheesecake de Dulce de Leche', 'Porción individual', 6)], 'notes': ''},
    {'customer': 1, 'status': 'confirmed', 'days': 2, 'created': 2, 'zone': None,
     'items': [('Brownie con Chips de Chocolate Blanco', 'Caja x6', 1), ('Cookie Doble Chocolate', 'Unidad', 4)],
     'notes': ''},
    {'customer': 4, 'status': 'deposit_paid', 'days': 3, 'created': 1, 'zone': 'GBA — Zona Norte',
     'items': [('Torta de Chocolate', '1/2 (8-10 porciones)', 1)], 'notes': 'Escribir "Feliz cumple Ana" en la torta.'},
    {'customer': 7, 'status': 'pending_deposit', 'days': 4, 'created': 1, 'zone': None,
     'items': [('Budín de Banana y Nuez', 'Pequeño (6 porciones)', 1)], 'notes': ''},
    {'customer': 3, 'status': 'pending_deposit', 'days': 6, 'created': 0, 'zone': 'CABA — Sur',
     'items': [('Cookie Chocolate Chips', 'Caja x4', 2)], 'notes': 'Si puede ser después de las 17hs, mejor.'},
]

# Recorrido de estados hasta el estado final de cada pedido
STATUS_FLOW = ['pending_deposit', 'deposit_paid', 'confirmed', 'in_production', 'ready']


class Command(BaseCommand):
    help = 'Carga el seed data de Dulceras Team'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Elimina y recrea todos los datos del tenant')
        parser.add_argument('--admin-password', default='admin1234', help='Contraseña del usuario admin (default: admin1234)')
        parser.add_argument('--skip-orders', action='store_true', help='No crear clientes ni pedidos de demo')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            # FKs con PROTECT (pago→pedido, pedido→cliente/variante, producto→categoría):
            # borrar en orden antes del tenant
            from payments.models import PaymentIntent
            PaymentIntent.objects.filter(order__tenant__slug=TENANT_SLUG).delete()
            Order.objects.filter(tenant__slug=TENANT_SLUG).delete()
            Product.objects.filter(tenant__slug=TENANT_SLUG).delete()
            Tenant.objects.filter(slug=TENANT_SLUG).delete()
            self.stdout.write(self.style.WARNING('Tenant Dulceras Team eliminado.'))

        # Plans
        PLANS = [
            {
                'slug': 'basico', 'name': 'Básico',
                'price_monthly': Decimal('0'),
                'description': 'Para empezar. Ideal para emprendimientos chicos.',
                'max_products': 10, 'max_users': 2, 'max_orders_per_day': 20,
                'has_mp_integration': False, 'has_whatsapp': False,
            },
            {
                'slug': 'pro', 'name': 'Pro',
                'price_monthly': Decimal('15000'),
                'description': 'Para negocios en crecimiento. Incluye Mercado Pago y WhatsApp.',
                'max_products': 50, 'max_users': 5, 'max_orders_per_day': 0,
                'has_mp_integration': True, 'has_whatsapp': True,
            },
            {
                'slug': 'enterprise', 'name': 'Enterprise',
                'price_monthly': Decimal('35000'),
                'description': 'Sin límites. Para negocios consolidados.',
                'max_products': 0, 'max_users': 0, 'max_orders_per_day': 0,
                'has_mp_integration': True, 'has_whatsapp': True,
            },
        ]
        for plan_data in PLANS:
            slug = plan_data.pop('slug')
            obj, created = Plan.objects.update_or_create(
                slug=slug,
                defaults=plan_data,
            )
            self.stdout.write(f"  {'+' if created else '~'} Plan: {obj.name} (${obj.price_monthly}/mes)")

        # Tenant
        pro_plan = Plan.objects.get(slug='pro')
        tenant, created = Tenant.objects.get_or_create(
            slug=TENANT_SLUG,
            defaults={'name': 'Dulceras Team', 'is_active': True, 'plan': pro_plan},
        )
        if not created and tenant.plan is None:
            tenant.plan = pro_plan
            tenant.save(update_fields=['plan'])
        self.stdout.write(f"{'Creado' if created else 'Existente'}: Tenant '{tenant.name}' (plan: {tenant.plan})")

        # Business profile
        profile, bp_created = BusinessProfile.objects.get_or_create(
            tenant=tenant,
            defaults={
                'address': 'Almagro, Ciudad Autónoma de Buenos Aires',
                'phone': '',
                'email': 'dulcerasteam@gmail.com',
                'whatsapp': '',
                'instagram': '@dulceras.team',
                'advance_hours_required': 48,
                'deposit_percentage': Decimal('50'),
                'primary_color': '#3D1A0E',
                'accent_color': '#E8889A',
                'bg_color': '#FDF6EC',
            },
        )
        if not bp_created:
            profile.primary_color = '#3D1A0E'
            profile.accent_color = '#E8889A'
            profile.bg_color = '#FDF6EC'
            profile.save(update_fields=['primary_color', 'accent_color', 'bg_color'])
        self.stdout.write(f"  {'+ ' if bp_created else '~ '}BusinessProfile")

        # Delivery zones
        for zone_data in DELIVERY_ZONES:
            obj, created = DeliveryZone.objects.get_or_create(
                tenant=tenant,
                name=zone_data['name'],
                defaults={
                    'description': zone_data['description'],
                    'price': zone_data['price'],
                    'is_active': True,
                },
            )
            self.stdout.write(f"  {'+' if created else '~'} Zona: {obj.name} (${obj.price})")

        # Categories
        category_map = {}
        for i, cat_data in enumerate(CATEGORIES):
            obj, created = Category.objects.get_or_create(
                tenant=tenant,
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'is_active': True,
                },
            )
            category_map[cat_data['slug']] = obj
            self.stdout.write(f"  {'+' if created else '~'} Categoría: {obj.name}")

        # Products & variants
        for i, prod_data in enumerate(PRODUCTS):
            category = category_map[prod_data['category_slug']]
            product, created = Product.objects.get_or_create(
                tenant=tenant,
                name=prod_data['name'],
                defaults={
                    'category': category,
                    'description': prod_data['description'],
                    'is_active': True,
                    'requires_advance_hours': prod_data['requires_advance_hours'],
                    'sort_order': i,
                },
            )
            self.stdout.write(f"  {'+' if created else '~'} Producto: {product.name}")

            for j, var_data in enumerate(prod_data['variants']):
                variant, v_created = ProductVariant.objects.get_or_create(
                    tenant=tenant,
                    product=product,
                    name=var_data['name'],
                    defaults={
                        'price': var_data['price'],
                        'stock_quantity': 0,
                        'is_active': True,
                        'sort_order': j,
                    },
                )
                self.stdout.write(f"      {'+' if v_created else '~'} {variant.name} — ${variant.price}")

        # Admin user
        admin_password = options['admin_password']
        existing_admin = User.objects.filter(username='admin').first()
        if existing_admin and existing_admin.tenant_id != tenant.id:
            # Tras --reset el usuario queda sin tenant: reasignarlo en lugar de duplicarlo
            existing_admin.tenant = tenant
            existing_admin.save(update_fields=['tenant'])
            self.stdout.write('  ~ Usuario admin reasignado al tenant')
        elif not existing_admin:
            User.objects.create_user(
                username='admin',
                password=admin_password,
                email='dulcerasteam@gmail.com',
                tenant=tenant,
                role=User.TENANT_ADMIN,
            )
            self.stdout.write(f"  + Usuario admin (contraseña: {admin_password})")
        else:
            self.stdout.write('  ~ Usuario admin ya existe')

        # Subscription
        sub, sub_created = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={
                'plan': pro_plan,
                'status': Subscription.ACTIVE,
                'current_period_end': timezone.now() + timedelta(days=365),
            },
        )
        if not sub_created and sub.status == Subscription.TRIAL:
            sub.status = Subscription.ACTIVE
            sub.plan = pro_plan
            sub.current_period_end = timezone.now() + timedelta(days=365)
            sub.save(update_fields=['status', 'plan', 'current_period_end', 'updated_at'])
        self.stdout.write(f"  {'+ ' if sub_created else '~ '}Subscription: {sub.status}")

        if not options['skip_orders']:
            self._seed_demo_orders(tenant)

        self.stdout.write(self.style.SUCCESS('\nSeed de Dulceras Team completado.'))

    def _seed_demo_orders(self, tenant):
        if Order.objects.filter(tenant=tenant, internal_notes=DEMO_ORDER_MARKER).exists():
            self.stdout.write('  ~ Pedidos de demo ya existen (usar --reset para recrearlos)')
            return

        admin = User.objects.filter(tenant=tenant, role=User.TENANT_ADMIN).first()
        zones = {z.name: z for z in DeliveryZone.objects.filter(tenant=tenant)}
        variants = {
            (v.product.name, v.name): v
            for v in ProductVariant.objects.filter(tenant=tenant).select_related('product')
        }

        customers = []
        for data in DEMO_CUSTOMERS:
            customer, _ = Customer.objects.get_or_create(
                tenant=tenant, name=data['name'],
                defaults={'phone': data['phone'], 'email': data['email']},
            )
            address = None
            if data['address']:
                address, _ = CustomerAddress.objects.get_or_create(
                    customer=customer, street=data['address']['street'],
                    defaults={
                        'neighborhood': data['address']['neighborhood'],
                        'city': data['address'].get('city', 'Buenos Aires'),
                        'is_default': True,
                    },
                )
            customers.append((customer, address))

        now = timezone.now()
        today = timezone.localdate()
        for data in DEMO_ORDERS:
            customer, address = customers[data['customer']]
            zone = zones.get(data['zone']) if data['zone'] else None
            rows = []
            for product_name, variant_name, qty in data['items']:
                variant = variants[(product_name, variant_name)]
                rows.append((variant, qty, variant.price * qty))

            subtotal = sum(r[2] for r in rows)
            delivery_cost = zone.price if zone else Decimal('0')
            total = subtotal + delivery_cost
            deposit_pct = Decimal('50')
            deposit = (total * deposit_pct / 100).quantize(Decimal('1'))

            order = Order.objects.create(
                tenant=tenant,
                customer=customer,
                status=data['status'],
                delivery_method=Order.DELIVERY if zone else Order.PICKUP,
                delivery_zone=zone,
                delivery_address=address if zone else None,
                required_date=today + timedelta(days=data['days']),
                subtotal=subtotal,
                delivery_cost=delivery_cost,
                total=total,
                deposit_percentage=deposit_pct,
                deposit_amount=deposit,
                balance_amount=total - deposit,
                notes=data['notes'],
                internal_notes=DEMO_ORDER_MARKER,
            )
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order, product_variant=variant, product_name=variant.product.name,
                    variant_name=variant.name, unit_price=variant.price, quantity=qty, subtotal=line,
                )
                for variant, qty, line in rows
            ])

            created_at = now - timedelta(days=data['created'], hours=2)
            Order.objects.filter(pk=order.pk).update(created_at=created_at)
            self._seed_status_history(order, data['status'], created_at, admin)
            self.stdout.write(
                f"  + Pedido #{order.pk}: {customer.name} — {order.get_status_display()} — ${total}"
            )

    def _seed_status_history(self, order, final_status, created_at, admin):
        if final_status == Order.CANCELLED:
            steps = ['pending_deposit', 'deposit_paid', 'cancelled']
        elif final_status in ('out_for_delivery', 'delivered'):
            steps = STATUS_FLOW + (['out_for_delivery'] if order.delivery_method == Order.DELIVERY else [])
            if final_status == 'delivered':
                steps.append('delivered')
        else:
            steps = STATUS_FLOW[:STATUS_FLOW.index(final_status) + 1]

        prev = ''
        for i, step in enumerate(steps):
            entry = OrderStatusHistory.objects.create(
                order=order,
                from_status=prev,
                to_status=step,
                # La seña la confirma Mercado Pago (sin usuario); el resto, el admin
                changed_by=admin if step not in ('pending_deposit', 'deposit_paid') else None,
                notes='Pedido creado via checkout' if i == 0 else '',
            )
            OrderStatusHistory.objects.filter(pk=entry.pk).update(changed_at=created_at + timedelta(hours=3 * i))
            prev = step

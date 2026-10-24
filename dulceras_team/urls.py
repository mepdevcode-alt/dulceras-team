from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenRefreshView
from users.views import CustomTokenObtainPairView

from tenants.urls import public_urlpatterns as tenants_public, admin_urlpatterns as tenants_admin
from audit.urls import superadmin_urlpatterns
from catalog.urls import public_urlpatterns as catalog_public, admin_urlpatterns as catalog_admin
from orders.urls import public_urlpatterns as orders_public, admin_urlpatterns as orders_admin, coupon_urlpatterns as coupons_admin, template_urlpatterns as orders_templates
from customers.urls import admin_urlpatterns as customers_admin, admin_review_urlpatterns as reviews_admin, public_urlpatterns as customers_public
from payments.urls import public_urlpatterns as payments_public, admin_urlpatterns as payments_admin, template_urlpatterns as payments_templates
from notifications.urls import admin_urlpatterns as notifications_admin, n8n_urlpatterns
from dulceras_team import pages

public_patterns = [*tenants_public, *catalog_public, *orders_public, *payments_public, *customers_public]

urlpatterns = [
    # ── Template pages (HTML, server-rendered) ─────────────────────────────────
    *payments_templates,
    *orders_templates,

    # Public pages
    path('', pages.landing, name='landing'),
    path('catalogo/', pages.catalog, name='catalog'),
    path('checkout/', pages.checkout, name='checkout'),

    # Customer account
    path('cuenta/login/', pages.cuenta_login, name='cuenta-login'),
    path('cuenta/registro/', pages.cuenta_registro, name='cuenta-registro'),
    path('cuenta/pedidos/', pages.cuenta_pedidos, name='cuenta-pedidos'),

    # Admin panel (must be before path('admin/', admin.site.urls))
    path('admin/login/', pages.admin_login, name='admin-login'),
    path('admin/dashboard/', pages.admin_dashboard, name='admin-dashboard'),
    path('admin/orders/', pages.admin_orders, name='admin-orders'),
    path('admin/orders/<int:order_id>/', pages.admin_order_detail, name='admin-order-detail'),
    path('admin/customers/', pages.admin_customers, name='admin-customers'),
    path('admin/catalog/', pages.admin_catalog, name='admin-catalog'),
    path('admin/calendar/', pages.admin_calendar, name='admin-calendar'),
    path('admin/reports/', pages.admin_reports, name='admin-reports'),
    path('admin/settings/', pages.admin_settings, name='admin-settings'),
    path('admin/coupons/', pages.admin_coupons, name='admin-coupons'),
    path('admin/reviews/', pages.admin_reviews, name='admin-reviews'),

    # Superadmin: panel Sistema
    path('superadmin/', pages.superadmin_system, name='superadmin-system'),
    path('superadmin/metrics/', RedirectView.as_view(pattern_name='superadmin-system')),

    # Django admin
    path('admin/', admin.site.urls),

    # JWT auth
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token-obtain'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Public API (no auth)
    path('api/public/', include(public_patterns)),

    # Admin API (JWT required)
    path('api/admin/', include(tenants_admin)),
    path('api/admin/catalog/', include(catalog_admin)),
    path('api/admin/orders/', include(orders_admin)),
    path('api/admin/coupons/', include(coupons_admin)),
    path('api/admin/customers/', include(customers_admin)),
    path('api/admin/reviews/', include(reviews_admin)),
    path('api/admin/', include(payments_admin)),
    path('api/admin/', include(notifications_admin)),

    # Panel Sistema (rol superadmin)
    path('api/superadmin/', include(superadmin_urlpatterns)),

    # Callbacks de n8n (secreto compartido)
    path('api/n8n/', include(n8n_urlpatterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

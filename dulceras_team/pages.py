"""Template views for server-rendered pages."""
from django.shortcuts import render


# ── Public ─────────────────────────────────────────────────────────────────────

def landing(request):
    from catalog.models import Product
    from customers.models import Review
    products = list(
        Product.objects
        .filter(is_active=True)
        .select_related('category')
        .prefetch_related('variants')
        .order_by('sort_order', 'name')[:9]
    )
    for p in products:
        active = [v for v in p.variants.all() if v.is_active]
        prices = [float(v.price) for v in active if float(v.price) > 0]
        p.min_price = min(prices) if prices else None
        p.has_stock = any(v.stock_quantity > 0 for v in active)
    reviews = list(Review.objects.filter(is_approved=True)[:12])
    return render(request, 'landing/home.html', {'products': products, 'reviews': reviews})


def catalog(request):
    from catalog.models import Category, Product
    categories = list(Category.objects.filter(is_active=True).order_by('name'))
    products = list(
        Product.objects
        .filter(is_active=True)
        .select_related('category')
        .prefetch_related('variants')
        .order_by('sort_order', 'name')
    )
    for p in products:
        active = [v for v in p.variants.all() if v.is_active]
        prices = [float(v.price) for v in active if float(v.price) > 0]
        p.min_price = min(prices) if prices else None
        p.has_stock = any(v.stock_quantity > 0 for v in active)
        # price as int avoids locale comma-decimal issue in Alpine JS expressions
        p.active_variants = [
            {'id': v.id, 'name': v.name, 'price': int(v.price), 'stock_quantity': v.stock_quantity}
            for v in active
        ]
    return render(request, 'catalog/catalog.html', {
        'categories': categories,
        'products': products,
    })


def checkout(request):
    return render(request, 'checkout/checkout.html')


# ── Customer account ───────────────────────────────────────────────────────────

def cuenta_login(request):
    return render(request, 'cuenta/login.html')


def cuenta_registro(request):
    return render(request, 'cuenta/registro.html')


def cuenta_pedidos(request):
    return render(request, 'cuenta/orders.html')


# ── Admin panel (admin / staff) ────────────────────────────────────────────────

def admin_login(request):
    return render(request, 'admin_panel/login.html')


def admin_dashboard(request):
    return render(request, 'admin_panel/dashboard.html')


def admin_orders(request):
    return render(request, 'admin_panel/orders.html')


def admin_order_detail(request, order_id):
    return render(request, 'admin_panel/order_detail.html', {'order_id': order_id})


def admin_customers(request):
    return render(request, 'admin_panel/customers.html')


def admin_catalog(request):
    return render(request, 'admin_panel/catalog.html')


def admin_calendar(request):
    return render(request, 'admin_panel/calendar.html')


def admin_reports(request):
    return render(request, 'admin_panel/reports.html')


def admin_settings(request):
    return render(request, 'admin_panel/settings.html')


def admin_coupons(request):
    return render(request, 'admin_panel/coupons.html')


def admin_reviews(request):
    return render(request, 'admin_panel/reviews.html')


# ── Superadmin: panel Sistema ──────────────────────────────────────────────────

def superadmin_system(request):
    return render(request, 'superadmin/system.html')

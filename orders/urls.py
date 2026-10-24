from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    PublicCouponValidateView, PublicDateAvailabilityView,
    PublicOrderCreateView, PublicOrderDetailView,
    AdminCouponViewSet, AdminOrderViewSet,
    order_confirmation,
)

# URL patterns para las páginas HTML (template views)
template_urlpatterns = [
    path('pedido/<int:order_id>/', order_confirmation, name='order-confirmation'),
]

public_urlpatterns = [
    path('orders/', PublicOrderCreateView.as_view(), name='public-order-create'),
    path('orders/<int:pk>/', PublicOrderDetailView.as_view(), name='public-order-detail'),
    path('calendar/availability/', PublicDateAvailabilityView.as_view(), name='public-date-availability'),
    path('coupons/validate/', PublicCouponValidateView.as_view(), name='public-coupon-validate'),
]

order_router = DefaultRouter()
order_router.register('', AdminOrderViewSet, basename='admin-orders')
admin_urlpatterns = order_router.urls

coupon_router = DefaultRouter()
coupon_router.register('', AdminCouponViewSet, basename='admin-coupons')
coupon_urlpatterns = coupon_router.urls

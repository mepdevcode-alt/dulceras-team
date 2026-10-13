from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    AdminCustomerViewSet, AdminReviewViewSet,
    CustomerRegisterView, CustomerLoginView,
    CustomerProfileView, CustomerOrdersView,
    ReviewListView, CustomerReviewCreateView,
)

router = DefaultRouter()
router.register('', AdminCustomerViewSet, basename='admin-customers')

reviews_router = DefaultRouter()
reviews_router.register('', AdminReviewViewSet, basename='admin-reviews')

admin_urlpatterns = router.urls
admin_review_urlpatterns = reviews_router.urls

public_urlpatterns = [
    path('customers/register/', CustomerRegisterView.as_view(), name='customer-register'),
    path('customers/login/', CustomerLoginView.as_view(), name='customer-login'),
    path('customers/me/', CustomerProfileView.as_view(), name='customer-me'),
    path('customers/me/orders/', CustomerOrdersView.as_view(), name='customer-orders'),
    path('customers/me/reviews/', CustomerReviewCreateView.as_view(), name='customer-review-create'),
    path('reviews/', ReviewListView.as_view(), name='public-reviews'),
]

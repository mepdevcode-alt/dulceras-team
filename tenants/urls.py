from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminDeliveryZoneViewSet, BusinessSettingsView, PublicBrandingView, PublicDeliveryZoneListView,
)

public_urlpatterns = [
    path('delivery-zones/', PublicDeliveryZoneListView.as_view(), name='public-delivery-zones'),
    path('branding/', PublicBrandingView.as_view(), name='public-branding'),
]

admin_router = DefaultRouter()
admin_router.register('delivery-zones', AdminDeliveryZoneViewSet, basename='admin-delivery-zones')

admin_urlpatterns = [
    path('settings/', BusinessSettingsView.as_view(), name='business-settings'),
    path('', include(admin_router.urls)),
]

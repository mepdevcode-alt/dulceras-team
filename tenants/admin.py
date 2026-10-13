from django.contrib import admin
from .models import BusinessProfile, DeliveryZone


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'deposit_percentage')

    def has_add_permission(self, request):
        # Registro único: solo se edita el existente
        return not BusinessProfile.objects.exists()


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

from rest_framework import serializers, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsTeamMember
from .models import BusinessProfile, DeliveryZone


# ── Public ────────────────────────────────────────────────────────────────────

class PublicBrandingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        profile = BusinessProfile.load()
        return Response({
            'business_name': profile.name,
            'logo_url': profile.logo_url,
            'primary_color': profile.primary_color,
            'accent_color': profile.accent_color,
            'bg_color': profile.bg_color,
        })


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ('id', 'name', 'description', 'price')


class PublicDeliveryZoneListView(ListAPIView):
    serializer_class = DeliveryZoneSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return DeliveryZone.objects.filter(is_active=True).order_by('price')


# ── Admin delivery zones ──────────────────────────────────────────────────────

class AdminDeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ('id', 'name', 'description', 'price', 'is_active')


class AdminDeliveryZoneViewSet(viewsets.ModelViewSet):
    serializer_class = AdminDeliveryZoneSerializer
    permission_classes = [IsTeamMember]
    pagination_class = None
    queryset = DeliveryZone.objects.order_by('price')


# ── Admin: configuración del negocio ─────────────────────────────────────────

class BusinessSettingsSerializer(serializers.ModelSerializer):
    primary_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)
    accent_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)
    bg_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)

    class Meta:
        model = BusinessProfile
        fields = (
            'name', 'address', 'phone', 'email', 'whatsapp', 'instagram',
            'advance_hours_required', 'deposit_percentage', 'max_orders_per_day',
            'logo_url', 'primary_color', 'accent_color', 'bg_color',
        )


class BusinessSettingsView(APIView):
    permission_classes = [IsTeamMember]

    def get(self, request):
        return Response(BusinessSettingsSerializer(BusinessProfile.load()).data)

    def patch(self, request):
        serializer = BusinessSettingsSerializer(BusinessProfile.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

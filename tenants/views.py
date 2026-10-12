from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from django.utils import timezone
from datetime import timedelta
from .models import BusinessProfile, Plan, Subscription, Tenant, DeliveryZone
from users.permissions import IsTeamMember

User = get_user_model()


# ── Permission ────────────────────────────────────────────────────────────────

class IsPlatformOwner(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_platform_owner


# ── Public ────────────────────────────────────────────────────────────────────

class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            'id', 'name', 'slug', 'price_monthly', 'description',
            'max_products', 'max_users', 'max_orders_per_day',
            'has_mp_integration', 'has_whatsapp',
        )


class PublicBrandingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        profile, _ = BusinessProfile.objects.get_or_create(tenant=tenant)
        return Response({
            'business_name': tenant.name,
            'logo_url': profile.logo_url,
            'primary_color': profile.primary_color,
            'accent_color': profile.accent_color,
            'bg_color': profile.bg_color,
        })


class PublicPlanListView(ListAPIView):
    serializer_class = PublicPlanSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return Plan.objects.filter(is_active=True).order_by('price_monthly')


class RegisterSerializer(serializers.Serializer):
    # Business
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=50)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    whatsapp = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    # Admin user
    admin_username = serializers.CharField(max_length=150)
    admin_password = serializers.CharField(min_length=8)
    admin_email = serializers.EmailField(required=False, allow_blank=True, default='')
    # Plan (optional)
    plan_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError('Ya existe un negocio con ese slug.')
        return value

    def validate_admin_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Ese nombre de usuario ya está en uso.')
        return value

    def validate_plan_id(self, value):
        if value is not None and not Plan.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError('Plan no válido.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        plan = None
        plan_id = validated_data.get('plan_id')
        if plan_id:
            plan = Plan.objects.get(pk=plan_id)

        tenant = Tenant.objects.create(
            name=validated_data['name'],
            slug=validated_data['slug'],
            plan=plan,
        )
        BusinessProfile.objects.create(
            tenant=tenant,
            phone=validated_data.get('phone', ''),
            email=validated_data.get('email', ''),
            whatsapp=validated_data.get('whatsapp', ''),
        )
        user = User.objects.create_user(
            username=validated_data['admin_username'],
            password=validated_data['admin_password'],
            email=validated_data.get('admin_email', ''),
            tenant=tenant,
            role=User.TENANT_ADMIN,
        )
        return tenant, user


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant, user = serializer.save()
        plan = tenant.plan
        Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=Subscription.TRIAL,
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        return Response(
            {
                'tenant_name': tenant.name,
                'tenant_slug': tenant.slug,
                'admin_username': user.username,
            },
            status=status.HTTP_201_CREATED,
        )


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ('id', 'name', 'description', 'price')


class PublicDeliveryZoneListView(ListAPIView):
    serializer_class = DeliveryZoneSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        tenant = get_object_or_404(Tenant, slug=self.kwargs['tenant_slug'], is_active=True)
        return DeliveryZone.objects.filter(tenant=tenant, is_active=True).order_by('price')


# ── Superadmin serializers ────────────────────────────────────────────────────

class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = (
            'address', 'phone', 'email', 'whatsapp', 'instagram',
            'advance_hours_required', 'deposit_percentage', 'max_orders_per_day',
        )


class TenantPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('id', 'name', 'slug', 'price_monthly')


class TenantListSerializer(serializers.ModelSerializer):
    profile = BusinessProfileSerializer(read_only=True)
    plan = TenantPlanSerializer(read_only=True)
    order_count = serializers.IntegerField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tenant
        fields = ('id', 'name', 'slug', 'is_active', 'plan', 'profile', 'order_count', 'user_count', 'created_at')
        read_only_fields = ('id', 'created_at')


class TenantCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=50)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    whatsapp = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    instagram = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    admin_username = serializers.CharField(max_length=150)
    admin_password = serializers.CharField(min_length=8)
    admin_email = serializers.EmailField(required=False, allow_blank=True, default='')

    def validate_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError('Ya existe un negocio con ese slug.')
        return value

    def validate_admin_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Ese nombre de usuario ya está en uso.')
        return value

    @transaction.atomic
    def create(self, validated_data):
        tenant = Tenant.objects.create(
            name=validated_data['name'],
            slug=validated_data['slug'],
        )
        BusinessProfile.objects.create(
            tenant=tenant,
            address=validated_data.get('address', ''),
            phone=validated_data.get('phone', ''),
            email=validated_data.get('email', ''),
            whatsapp=validated_data.get('whatsapp', ''),
            instagram=validated_data.get('instagram', ''),
        )
        user = User.objects.create_user(
            username=validated_data['admin_username'],
            password=validated_data['admin_password'],
            email=validated_data.get('admin_email', ''),
            tenant=tenant,
            role=User.TENANT_ADMIN,
        )
        return tenant, user


class TenantUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'role', 'is_active', 'date_joined')
        read_only_fields = ('id', 'date_joined')


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=8)
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default=User.STAFF_VENTAS)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Ese nombre de usuario ya está en uso.')
        return value


# ── Superadmin views ──────────────────────────────────────────────────────────

class SuperadminTenantViewSet(viewsets.ViewSet):
    permission_classes = [IsPlatformOwner]

    def _annotate_tenants(self, qs):
        from orders.models import Order
        from django.db.models import OuterRef, Subquery, IntegerField
        order_count_sq = (
            Order.objects.filter(tenant=OuterRef('pk'))
            .values('tenant')
            .annotate(c=Count('id'))
            .values('c')
        )
        user_count_sq = (
            User.objects.filter(tenant=OuterRef('pk'))
            .values('tenant')
            .annotate(c=Count('id'))
            .values('c')
        )
        return qs.annotate(
            order_count=Subquery(order_count_sq, output_field=IntegerField()),
            user_count=Subquery(user_count_sq, output_field=IntegerField()),
        )

    def list(self, request):
        tenants = self._annotate_tenants(Tenant.objects.all()).order_by('-created_at')
        return Response(TenantListSerializer(tenants, many=True).data)

    def retrieve(self, request, pk=None):
        tenant = get_object_or_404(self._annotate_tenants(Tenant.objects.all()), pk=pk)
        users = User.objects.filter(tenant=tenant).order_by('username')
        from orders.models import Order
        revenue = Order.objects.filter(tenant=tenant, status__in=[
            'deposit_paid', 'confirmed', 'in_production', 'ready', 'out_for_delivery', 'delivered'
        ]).aggregate(total=Sum('total'))['total'] or 0
        return Response({
            **TenantListSerializer(tenant).data,
            'users': TenantUserSerializer(users, many=True).data,
            'revenue': float(revenue),
        })

    def create(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant, user = serializer.save()
        annotated = self._annotate_tenants(Tenant.objects.filter(pk=tenant.pk)).first()
        return Response(
            {'tenant': TenantListSerializer(annotated).data, 'admin_username': user.username},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='toggle')
    def toggle(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        tenant.is_active = not tenant.is_active
        tenant.save(update_fields=['is_active'])
        return Response({'is_active': tenant.is_active})

    @action(detail=True, methods=['patch'], url_path='profile')
    def update_profile(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        profile, _ = BusinessProfile.objects.get_or_create(tenant=tenant)
        serializer = BusinessProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='users')
    def add_user(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        plan = tenant.plan
        if plan and plan.max_users > 0:
            current = User.objects.filter(tenant=tenant).count()
            if current >= plan.max_users:
                return Response(
                    {'detail': f'El plan "{plan.name}" permite hasta {plan.max_users} usuario(s). Actualizá el plan para agregar más.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        user = User.objects.create_user(
            username=d['username'],
            password=d['password'],
            email=d.get('email', ''),
            tenant=tenant,
            role=d['role'],
        )
        return Response(TenantUserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='plan')
    def assign_plan(self, request, pk=None):
        tenant = get_object_or_404(Tenant, pk=pk)
        plan_id = request.data.get('plan_id')
        plan = None if plan_id is None else get_object_or_404(Plan, pk=plan_id)
        tenant.plan = plan
        tenant.save(update_fields=['plan'])
        sub, _ = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={'plan': plan, 'status': Subscription.TRIAL, 'trial_ends_at': timezone.now() + timedelta(days=14)},
        )
        if sub.plan != plan:
            sub.plan = plan
            sub.save(update_fields=['plan', 'updated_at'])
        annotated = self._annotate_tenants(Tenant.objects.filter(pk=tenant.pk)).first()
        return Response(TenantListSerializer(annotated).data)

    @action(detail=False, methods=['get'], url_path='metrics')
    def metrics(self, request):
        from orders.models import Order
        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(is_active=True).count()
        total_orders = Order.objects.count()
        total_revenue = Order.objects.filter(status__in=[
            'deposit_paid', 'confirmed', 'in_production', 'ready', 'out_for_delivery', 'delivered'
        ]).aggregate(t=Sum('total'))['t'] or 0
        total_users = User.objects.filter(role__in=[
            User.TENANT_ADMIN, User.STAFF_VENTAS, User.STAFF_PRODUCCION, User.STAFF_CAJA
        ]).count()
        from orders.models import Order as Ord
        from django.db.models import OuterRef, Subquery, IntegerField
        ocount_sq = (
            Ord.objects.filter(tenant=OuterRef('pk'))
            .values('tenant').annotate(c=Count('id')).values('c')
        )
        by_tenant = list(
            Tenant.objects
            .annotate(orders=Subquery(ocount_sq, output_field=IntegerField()))
            .values('id', 'name', 'slug', 'is_active', 'orders')
            .order_by('-orders')
        )
        return Response({
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'total_orders': total_orders,
            'total_revenue': float(total_revenue),
            'total_users': total_users,
            'by_tenant': by_tenant,
        })


# ── Plans ─────────────────────────────────────────────────────────────────────

class PlanSerializer(serializers.ModelSerializer):
    tenant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = (
            'id', 'name', 'slug', 'price_monthly', 'description',
            'max_products', 'max_users', 'max_orders_per_day',
            'has_mp_integration', 'has_whatsapp', 'is_active',
            'tenant_count', 'created_at',
        )
        read_only_fields = ('id', 'created_at')


class PlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformOwner]
    serializer_class = PlanSerializer

    def get_queryset(self):
        from django.db.models import Count as DjCount
        return (
            Plan.objects
            .annotate(tenant_count=DjCount('tenant', distinct=True))
            .order_by('price_monthly')
        )


# ── Admin delivery zones ──────────────────────────────────────────────────────

class AdminDeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ('id', 'name', 'description', 'price', 'is_active')


class AdminDeliveryZoneViewSet(viewsets.ModelViewSet):
    serializer_class = AdminDeliveryZoneSerializer
    permission_classes = [IsTeamMember]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_owner:
            slug = self.request.query_params.get('tenant')
            if slug:
                tenant = get_object_or_404(Tenant, slug=slug)
                return DeliveryZone.objects.filter(tenant=tenant).order_by('price')
            if user.tenant:
                return DeliveryZone.objects.filter(tenant=user.tenant).order_by('price')
            return DeliveryZone.objects.none()
        return DeliveryZone.objects.filter(tenant=user.tenant).order_by('price')

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_platform_owner:
            slug = self.request.query_params.get('tenant')
            tenant = get_object_or_404(Tenant, slug=slug) if slug else user.tenant
        else:
            tenant = user.tenant
        serializer.save(tenant=tenant)


# ── Admin settings (tenant propio) ───────────────────────────────────────────

class TenantSettingsSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    whatsapp = serializers.CharField(max_length=50, required=False, allow_blank=True)
    instagram = serializers.CharField(max_length=100, required=False, allow_blank=True)
    advance_hours_required = serializers.IntegerField(min_value=0, required=False)
    deposit_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    max_orders_per_day = serializers.IntegerField(min_value=0, required=False)
    logo_url = serializers.URLField(required=False, allow_blank=True)
    primary_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)
    accent_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)
    bg_color = serializers.RegexField(r'^#[0-9A-Fa-f]{6}$', required=False)


class TenantSettingsView(APIView):
    permission_classes = [IsTeamMember]

    def _get_tenant(self):
        user = self.request.user
        if user.is_platform_owner:
            slug = self.request.query_params.get('tenant')
            if slug:
                return get_object_or_404(Tenant, slug=slug)
            return user.tenant
        return user.tenant

    def get(self, request):
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)
        profile, _ = BusinessProfile.objects.get_or_create(tenant=tenant)
        return Response({
            'name': tenant.name,
            'slug': tenant.slug,
            'address': profile.address,
            'phone': profile.phone,
            'email': profile.email,
            'whatsapp': profile.whatsapp,
            'instagram': profile.instagram,
            'advance_hours_required': profile.advance_hours_required,
            'deposit_percentage': str(profile.deposit_percentage),
            'max_orders_per_day': profile.max_orders_per_day,
            'logo_url': profile.logo_url,
            'primary_color': profile.primary_color,
            'accent_color': profile.accent_color,
            'bg_color': profile.bg_color,
        })

    def patch(self, request):
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)
        serializer = TenantSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        if 'name' in d:
            tenant.name = d['name']
            tenant.save(update_fields=['name'])

        profile, _ = BusinessProfile.objects.get_or_create(tenant=tenant)
        profile_fields = ['address', 'phone', 'email', 'whatsapp', 'instagram',
                          'advance_hours_required', 'deposit_percentage', 'max_orders_per_day',
                          'logo_url', 'primary_color', 'accent_color', 'bg_color']
        updated = [f for f in profile_fields if f in d]
        for f in updated:
            setattr(profile, f, d[f])
        if updated:
            profile.save(update_fields=updated)

        return self.get(request)


# ── Admin billing ─────────────────────────────────────────────────────────────

class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True, default=None)
    plan_price = serializers.DecimalField(source='plan.price_monthly', max_digits=10, decimal_places=2, read_only=True, default=None)
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            'id', 'status', 'plan_name', 'plan_price',
            'trial_ends_at', 'current_period_end', 'days_remaining',
        )

    def get_days_remaining(self, obj):
        now = timezone.now()
        if obj.status == Subscription.TRIAL and obj.trial_ends_at:
            delta = obj.trial_ends_at - now
            return max(0, delta.days)
        if obj.status == Subscription.ACTIVE and obj.current_period_end:
            delta = obj.current_period_end - now
            return max(0, delta.days)
        return None


class BillingView(APIView):
    permission_classes = [IsTeamMember]

    def _get_tenant(self):
        return self.request.user.tenant

    def get(self, request):
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)
        sub, _ = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={
                'plan': tenant.plan,
                'status': Subscription.TRIAL,
                'trial_ends_at': timezone.now() + timedelta(days=14),
            },
        )
        return Response(SubscriptionSerializer(sub).data)

    def post(self, request):
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'tenant requerido.'}, status=400)
        sub, _ = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={'plan': tenant.plan, 'status': Subscription.TRIAL, 'trial_ends_at': timezone.now() + timedelta(days=14)},
        )
        plan = sub.plan or tenant.plan
        if not plan or float(plan.price_monthly) == 0:
            return Response({'detail': 'Este plan no tiene costo mensual.'}, status=400)

        from payments.services import get_mp_sdk
        sdk = get_mp_sdk(tenant)
        if not sdk:
            return Response({'detail': 'Mercado Pago no configurado.', 'init_point': None})

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        notification_url = request.build_absolute_uri(
            f'/api/public/{tenant.slug}/webhooks/mp/'
        )
        preference_data = {
            'items': [{
                'title': f'Suscripción {plan.name} — {tenant.name}',
                'quantity': 1,
                'unit_price': float(plan.price_monthly),
                'currency_id': 'ARS',
            }],
            'back_urls': {
                'success': f'{frontend_url}/admin/billing?paid=1',
                'failure': f'{frontend_url}/admin/billing?failed=1',
                'pending': f'{frontend_url}/admin/billing?pending=1',
            },
            'auto_return': 'approved',
            'external_reference': f'sub_{sub.id}',
            'notification_url': notification_url,
        }
        result = sdk.preference().create(preference_data)
        preference = result.get('response', {})
        return Response({
            'init_point': preference.get('init_point'),
            'sandbox_init_point': preference.get('sandbox_init_point'),
            'amount': str(plan.price_monthly),
        })

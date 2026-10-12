from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.views import TenantFilterMixin
from tenants.models import Tenant
from users.models import User
from .models import Customer, CustomerAddress, Review
from .serializers import (
    CustomerListSerializer, CustomerDetailSerializer, CustomerWriteSerializer,
    CustomerAddressSerializer, CustomerAddressWriteSerializer,
    CustomerPublicRegisterSerializer, CustomerPublicProfileSerializer,
    CustomerPublicProfileUpdateSerializer,
    ReviewPublicSerializer, ReviewCreateSerializer, AdminReviewSerializer,
)
from users.permissions import IsTeamMember


class IsCustomerUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == User.CUSTOMER
        )


def _customer_tokens(customer_user):
    refresh = RefreshToken.for_user(customer_user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


# ── Públicas (sin auth) ───────────────────────────────────────────────────────

class CustomerRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        serializer = CustomerPublicRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        # Email único por tenant
        if User.objects.filter(email=d['email'], tenant=tenant, role=User.CUSTOMER).exists():
            return Response({'email': ['Ya existe una cuenta con ese email.']}, status=400)

        # Crear usuario
        customer_user = User.objects.create_user(
            username=d['email'],
            email=d['email'],
            password=d['password'],
            role=User.CUSTOMER,
            tenant=tenant,
            first_name=d['name'].split()[0] if d['name'].split() else d['name'],
        )

        # Buscar Customer existente por teléfono o crear uno nuevo
        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            phone=d['phone'],
            defaults={'name': d['name'], 'email': d['email']},
        )
        # Actualizar email si no lo tenía; linkar usuario
        if not customer.email:
            customer.email = d['email']
        customer.user = customer_user
        customer.save(update_fields=['user', 'email', 'updated_at'])

        return Response(
            {'tokens': _customer_tokens(customer_user),
             'customer': CustomerPublicProfileSerializer(customer).data},
            status=status.HTTP_201_CREATED,
        )


class CustomerLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        email = (request.data.get('email', '') or '').strip()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'detail': 'Email y contraseña son requeridos.'}, status=400)

        try:
            customer_user = User.objects.get(email=email, tenant=tenant, role=User.CUSTOMER)
        except User.DoesNotExist:
            return Response({'detail': 'Credenciales incorrectas.'}, status=401)

        if not customer_user.check_password(password):
            return Response({'detail': 'Credenciales incorrectas.'}, status=401)

        try:
            customer = customer_user.customer_profile
        except Customer.DoesNotExist:
            return Response({'detail': 'Cuenta sin perfil de cliente.'}, status=400)

        return Response({
            'tokens': _customer_tokens(customer_user),
            'customer': CustomerPublicProfileSerializer(customer).data,
        })


# ── Con auth de cliente ───────────────────────────────────────────────────────

class CustomerProfileView(APIView):
    permission_classes = [IsCustomerUser]

    def _get_customer(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        if request.user.tenant != tenant:
            return None
        return get_object_or_404(Customer, user=request.user, tenant=tenant)

    def get(self, request, tenant_slug):
        customer = self._get_customer(request, tenant_slug)
        if not customer:
            return Response({'detail': 'No autorizado.'}, status=403)
        return Response(CustomerPublicProfileSerializer(customer).data)

    def patch(self, request, tenant_slug):
        customer = self._get_customer(request, tenant_slug)
        if not customer:
            return Response({'detail': 'No autorizado.'}, status=403)
        serializer = CustomerPublicProfileUpdateSerializer(
            customer, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CustomerPublicProfileSerializer(customer).data)


class CustomerOrdersView(APIView):
    permission_classes = [IsCustomerUser]

    def get(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        if request.user.tenant != tenant:
            return Response({'detail': 'No autorizado.'}, status=403)

        from orders.models import Order
        from orders.serializers import OrderListSerializer

        orders = (
            Order.objects
            .filter(tenant=tenant, customer__user=request.user)
            .select_related('customer')
            .prefetch_related('items')
            .order_by('-created_at')
        )
        return Response(OrderListSerializer(orders, many=True).data)


class ReviewListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReviewPublicSerializer
    pagination_class = None

    def get_queryset(self):
        from catalog.views import get_active_tenant
        tenant = get_active_tenant(self.kwargs['tenant_slug'])
        return Review.objects.filter(tenant=tenant, is_approved=True)


class CustomerReviewCreateView(APIView):
    permission_classes = [IsCustomerUser]

    def post(self, request, tenant_slug):
        tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
        if request.user.tenant != tenant:
            return Response({'detail': 'No autorizado.'}, status=403)

        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            customer = request.user.customer_profile
        except Customer.DoesNotExist:
            return Response({'detail': 'Sin perfil de cliente.'}, status=400)

        review = Review.objects.create(
            tenant=tenant,
            customer=customer,
            author_name=customer.name,
            rating=serializer.validated_data['rating'],
            text=serializer.validated_data['text'],
        )
        return Response(ReviewPublicSerializer(review).data, status=status.HTTP_201_CREATED)


class AdminReviewViewSet(TenantFilterMixin, viewsets.ModelViewSet):
    permission_classes = [IsTeamMember]
    serializer_class = AdminReviewSerializer
    http_method_names = ['get', 'patch', 'head', 'options']
    pagination_class = None
    queryset = Review.objects.all().order_by('-created_at')

    def partial_update(self, request, *args, **kwargs):
        review = self.get_object()
        approved = request.data.get('is_approved')
        if approved is None:
            return Response({'detail': 'Campo is_approved requerido.'}, status=400)
        review.is_approved = bool(approved)
        review.save(update_fields=['is_approved'])
        return Response(AdminReviewSerializer(review).data)


class AdminCustomerViewSet(TenantFilterMixin, viewsets.ModelViewSet):
    permission_classes = [IsTeamMember]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    queryset = (
        Customer.objects
        .annotate(order_count=Count('orders'))
        .order_by('-created_at')
    )

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search)
            )
        ordering = self.request.query_params.get('ordering')
        if ordering in ('name', '-name'):
            qs = qs.order_by(ordering)
        return qs

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Los clientes no se pueden eliminar directamente.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        if self.action in ('create', 'partial_update', 'update'):
            return CustomerWriteSerializer
        return CustomerDetailSerializer

    # ── Addresses ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path='addresses')
    def addresses(self, request, pk=None):
        customer = self.get_object()
        if request.method == 'GET':
            return Response(
                CustomerAddressSerializer(customer.addresses.all(), many=True).data
            )
        serializer = CustomerAddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('is_default'):
            customer.addresses.update(is_default=False)
        address = serializer.save(customer=customer)
        return Response(CustomerAddressSerializer(address).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['patch', 'delete'],
        url_path=r'addresses/(?P<address_pk>\d+)',
    )
    def address_detail(self, request, pk=None, address_pk=None):
        customer = self.get_object()
        address = get_object_or_404(CustomerAddress, pk=address_pk, customer=customer)
        if request.method == 'DELETE':
            address.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = CustomerAddressWriteSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('is_default'):
            customer.addresses.exclude(pk=address_pk).update(is_default=False)
        address = serializer.save()
        return Response(CustomerAddressSerializer(address).data)

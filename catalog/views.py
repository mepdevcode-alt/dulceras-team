from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated


class AdminCatalogPagination(PageNumberPagination):
    page_size = 500
    max_page_size = 1000
    page_size_query_param = 'page_size'

from tenants.models import Tenant
from .models import Category, Product, ProductVariant
from .serializers import (
    CategoryPublicSerializer, ProductPublicSerializer,
    CategoryAdminSerializer, ProductAdminSerializer, ProductVariantAdminSerializer,
)
from users.permissions import IsTeamMember


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_active_tenant(tenant_slug):
    return get_object_or_404(Tenant, slug=tenant_slug, is_active=True)


# ── Público ───────────────────────────────────────────────────────────────────

class PublicCategoryListView(ListAPIView):
    serializer_class = CategoryPublicSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        tenant = get_active_tenant(self.kwargs['tenant_slug'])
        return Category.objects.filter(tenant=tenant, is_active=True).order_by('name')


class PublicProductListView(ListAPIView):
    serializer_class = ProductPublicSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        tenant = get_active_tenant(self.kwargs['tenant_slug'])
        qs = (
            Product.objects
            .filter(tenant=tenant, is_active=True)
            .select_related('category')
            .prefetch_related('variants')
        )
        category_slug = self.request.query_params.get('category')
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        return qs


class PublicProductDetailView(RetrieveAPIView):
    serializer_class = ProductPublicSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        tenant = get_active_tenant(self.kwargs['tenant_slug'])
        return get_object_or_404(
            Product.objects.select_related('category').prefetch_related('variants'),
            pk=self.kwargs['pk'],
            tenant=tenant,
            is_active=True,
        )


# ── Admin ─────────────────────────────────────────────────────────────────────

class TenantFilterMixin:
    """Filtra el queryset al tenant del usuario autenticado."""

    def get_tenant(self):
        user = self.request.user
        slug = self.request.query_params.get('tenant')
        if slug:
            return get_object_or_404(Tenant, slug=slug)
        if user.is_platform_owner:
            return None  # sin filtro → todos los tenants
        return user.tenant

    def perform_create(self, serializer):
        tenant = self.get_tenant() or get_object_or_404(
            Tenant, slug=self.request.query_params.get('tenant', '')
        )
        serializer.save(tenant=tenant)

    def get_queryset(self):
        tenant = self.get_tenant()
        if tenant is None and self.request.user.is_platform_owner:
            return self.queryset.all()  # .all() fuerza clon sin _result_cache
        if tenant is None:
            return self.queryset.model.objects.none()
        return self.queryset.filter(tenant=tenant)


class AdminCategoryViewSet(TenantFilterMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsTeamMember]
    pagination_class = AdminCatalogPagination


class AdminProductViewSet(TenantFilterMixin, viewsets.ModelViewSet):
    queryset = (
        Product.objects
        .select_related('category')
        .prefetch_related('variants')
        .order_by('sort_order', 'name')
    )
    serializer_class = ProductAdminSerializer
    permission_classes = [IsTeamMember]
    pagination_class = AdminCatalogPagination

    def perform_create(self, serializer):
        tenant = self.get_tenant() or get_object_or_404(
            Tenant, slug=self.request.query_params.get('tenant', '')
        )
        plan = getattr(tenant, 'plan', None)
        if plan and plan.max_products > 0:
            current = Product.objects.filter(tenant=tenant).count()
            if current >= plan.max_products:
                from rest_framework import serializers as drf_serializers
                raise drf_serializers.ValidationError(
                    f'Tu plan "{plan.name}" permite hasta {plan.max_products} productos. '
                    f'Actualizá tu plan para agregar más.'
                )
        serializer.save(tenant=tenant)


class AdminProductVariantViewSet(TenantFilterMixin, viewsets.ModelViewSet):
    queryset = ProductVariant.objects.select_related('product').order_by('sort_order', 'name')
    serializer_class = ProductVariantAdminSerializer
    permission_classes = [IsTeamMember]

    def perform_create(self, serializer):
        product = serializer.validated_data.get('product')
        if product:
            serializer.save(tenant=product.tenant)
        else:
            tenant = self.get_tenant() or get_object_or_404(
                Tenant, slug=self.request.query_params.get('tenant', '')
            )
            serializer.save(tenant=tenant)

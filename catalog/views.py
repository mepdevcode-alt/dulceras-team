from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from users.permissions import IsTeamMember
from .models import Category, Product, ProductVariant
from .serializers import (
    CategoryPublicSerializer, ProductPublicSerializer,
    CategoryAdminSerializer, ProductAdminSerializer, ProductVariantAdminSerializer,
)


class AdminCatalogPagination(PageNumberPagination):
    page_size = 500
    max_page_size = 1000
    page_size_query_param = 'page_size'


# ── Público ───────────────────────────────────────────────────────────────────

class PublicCategoryListView(ListAPIView):
    serializer_class = CategoryPublicSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by('name')


class PublicProductListView(ListAPIView):
    serializer_class = ProductPublicSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = (
            Product.objects
            .filter(is_active=True)
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
        return get_object_or_404(
            Product.objects.select_related('category').prefetch_related('variants'),
            pk=self.kwargs['pk'],
            is_active=True,
        )


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsTeamMember]
    pagination_class = AdminCatalogPagination


class AdminProductViewSet(viewsets.ModelViewSet):
    queryset = (
        Product.objects
        .select_related('category')
        .prefetch_related('variants')
        .order_by('sort_order', 'name')
    )
    serializer_class = ProductAdminSerializer
    permission_classes = [IsTeamMember]
    pagination_class = AdminCatalogPagination


class AdminProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.select_related('product').order_by('sort_order', 'name')
    serializer_class = ProductVariantAdminSerializer
    permission_classes = [IsTeamMember]

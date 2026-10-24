from rest_framework import serializers
from .models import Category, Product, ProductVariant


# ── Público ──────────────────────────────────────────────────────────────────

class CategoryPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description')


class ProductVariantPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ('id', 'name', 'price', 'stock_quantity')


class ProductPublicSerializer(serializers.ModelSerializer):
    category = CategoryPublicSerializer(read_only=True)
    variants = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'description', 'image_url',
            'requires_advance_hours', 'made_to_order', 'category', 'variants',
        )

    def get_variants(self, obj):
        active = obj.variants.filter(is_active=True)
        return ProductVariantPublicSerializer(active, many=True).data

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


# ── Admin ─────────────────────────────────────────────────────────────────────

class CategoryAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('created_at', 'updated_at')


class ProductVariantAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ('id', 'product', 'name', 'price', 'stock_quantity', 'is_active', 'sort_order')
        extra_kwargs = {'product': {'required': False}}


class ProductAdminSerializer(serializers.ModelSerializer):
    variants = ProductVariantAdminSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'category', 'category_name',
            'name', 'description', 'image', 'image_url',
            'is_active', 'made_to_order', 'requires_advance_hours', 'sort_order',
            'variants', 'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

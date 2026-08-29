from rest_framework import serializers

from .models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name_en", "name_ar", "slug", "description_en", "description_ar", "logo", "banner"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name_en", "name_ar", "slug", "parent", "image", "description_en", "description_ar"]


class ProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ["id", "attribute_type", "value_en", "value_ar", "slug"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "sort_order", "alt_text_en", "alt_text_ar"]


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "name_en", "name_ar", "sku_suffix", "price_delta", "stock"]


class RatingFieldsMixin(serializers.Serializer):
    """`average_rating` / `review_count` read straight off queryset annotations
    added by `Product.objects.with_ratings()` — a plain getattr, never a per-row
    query. Degrades safely (None / 0) if a caller forgot to annotate."""

    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    def get_average_rating(self, obj):
        val = getattr(obj, "average_rating", None)
        return round(float(val), 2) if val is not None else None

    def get_review_count(self, obj):
        return getattr(obj, "review_count", 0) or 0


class ProductListSerializer(RatingFieldsMixin, serializers.ModelSerializer):
    """Lean serializer for grid/listing pages — avoids shipping full descriptions
    and all images for every card in a 24-item page."""

    brand = BrandSerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    current_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name_en", "name_ar", "slug", "brand", "price", "sale_price",
            "current_price", "is_on_sale", "discount_percent", "badge_type", "in_stock",
            "primary_image", "pack_size", "average_rating", "review_count",
        ]

    def get_primary_image(self, obj):
        # Use the prefetched `images` cache (ProductListView prefetches it) and
        # sort in Python — `.order_by(...).first()` would re-query per row (N+1).
        images = list(obj.images.all())
        first = min(images, key=lambda i: i.sort_order) if images else None
        if not first:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(first.image.url) if request else first.image.url


class ProductDetailSerializer(RatingFieldsMixin, serializers.ModelSerializer):
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    current_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    benefits_en_list = serializers.SerializerMethodField()
    benefits_ar_list = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name_en", "name_ar", "slug",
            "description_en", "description_ar",
            "benefits_en", "benefits_ar", "benefits_en_list", "benefits_ar_list",
            "how_to_use_en", "how_to_use_ar",
            "brand", "category", "attributes", "images", "variants",
            "price", "sale_price", "current_price", "is_on_sale", "discount_percent",
            "stock", "in_stock", "pack_size", "badge_type",
            "average_rating", "review_count",
        ]

    def get_benefits_en_list(self, obj):
        return obj.benefits_list("en")

    def get_benefits_ar_list(self, obj):
        return obj.benefits_list("ar")

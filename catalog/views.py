from django.db.models import Q
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import ProductFilter
from .models import Brand, Category, Product, ProductAttribute
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductAttributeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)


class BrandListView(generics.ListAPIView):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    pagination_class = None  # a filter list, not a feed — return every brand


class BrandDetailView(generics.RetrieveAPIView):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    lookup_field = "slug"


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None  # the storefront filter dropdown needs the full taxonomy (60+ rows)

    def get_queryset(self):
        qs = Category.objects.filter(is_active=True).order_by("name_en")
        parent = self.request.query_params.get("parent")
        if parent is not None:
            qs = qs.filter(parent__slug=parent) if parent else qs.filter(parent__isnull=True)
        return qs


class SkinTypeListView(generics.ListAPIView):
    """GET /api/v1/skin-types/ — the skin_type ProductAttribute rows, for the
    Shop sidebar filter. Public, unpaginated, same shape as BrandListView."""

    queryset = ProductAttribute.objects.filter(attribute_type="skin_type").order_by("value_en")
    serializer_class = ProductAttributeSerializer
    pagination_class = None


class CategoryDetailView(generics.RetrieveAPIView):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = "slug"


class ProductListView(generics.ListAPIView):
    """GET /api/v1/products/?brand=&category=&skin_type=&badge=&search=&ordering=&page="""

    queryset = (
        Product.objects.filter(is_active=True)
        .with_ratings()
        .select_related("brand", "category")
        .prefetch_related("images")
    )
    serializer_class = ProductListSerializer
    filterset_class = ProductFilter
    search_fields = ["name_en", "name_ar", "sku", "description_en"]
    ordering_fields = ["price", "created_at", "name_en"]
    ordering = ["-created_at"]


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True).with_ratings().select_related("brand", "category")
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"


class ProductRecommendationsView(generics.ListAPIView):
    """GET /api/v1/products/{slug}/recommendations/ — same category first,
    falls back to same brand, excludes the product itself. Simple and
    explainable rather than a black-box similarity score, matching the
    'Related Products' + 'Complete Your Routine' spots on the product page."""

    serializer_class = ProductListSerializer
    pagination_class = None  # always a short fixed-size list, not a paginated page

    def get_queryset(self):
        product = generics.get_object_or_404(Product.objects.filter(is_active=True), slug=self.kwargs["slug"])
        qs = (
            Product.objects.filter(is_active=True)
            .with_ratings()
            .exclude(id=product.id)
            .select_related("brand")
            .prefetch_related("images")
        )
        if product.category_id:
            same_category = qs.filter(category_id=product.category_id)
            if same_category.exists():
                return same_category[:8]
        return qs.filter(brand_id=product.brand_id)[:8]


class SearchView(APIView):
    """GET /api/v1/search/?q= — combined products + categories + brands, as specced."""

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"products": [], "categories": [], "brands": []})

        products = Product.objects.filter(
            Q(is_active=True) & (Q(name_en__icontains=q) | Q(name_ar__icontains=q) | Q(sku__icontains=q))
        ).with_ratings().select_related("brand").prefetch_related("images")[:10]
        categories = Category.objects.filter(is_active=True, name_en__icontains=q)[:5]
        brands = Brand.objects.filter(is_active=True, name_en__icontains=q)[:5]

        return Response(
            {
                "products": ProductListSerializer(products, many=True, context={"request": request}).data,
                "categories": CategorySerializer(categories, many=True).data,
                "brands": BrandSerializer(brands, many=True).data,
            }
        )

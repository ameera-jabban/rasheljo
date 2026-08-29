import django_filters as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    brand = filters.CharFilter(field_name="brand__slug")
    category = filters.CharFilter(field_name="category__slug")
    skin_type = filters.CharFilter(field_name="attributes__slug", method="filter_skin_type")
    badge = filters.CharFilter(field_name="badge_type")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = ["brand", "category", "skin_type", "badge", "min_price", "max_price", "in_stock"]

    def filter_skin_type(self, queryset, name, value):
        return queryset.filter(attributes__attribute_type="skin_type", attributes__slug=value)

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)

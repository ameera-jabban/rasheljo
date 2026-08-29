from rest_framework import serializers

from catalog.models import Product
from catalog.serializers import ProductListSerializer

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product", write_only=True, queryset=Product.objects.filter(is_active=True)
    )
    unit_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "variant", "quantity", "unit_price", "line_total"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    discount_amount = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "subtotal", "coupon_code", "discount_amount", "total"]

    def get_discount_amount(self, obj):
        if not obj.coupon_code:
            return "0.00"
        from promotions.models import Coupon
        coupon = Coupon.objects.filter(code__iexact=obj.coupon_code).first()
        if not coupon or not coupon.is_valid_now()[0]:
            return "0.00"
        return f"{coupon.calculate_discount(obj.subtotal):.2f}"

    def get_total(self, obj):
        discount = float(self.get_discount_amount(obj))
        return f"{float(obj.subtotal) - discount:.2f}"

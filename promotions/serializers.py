from rest_framework import serializers

from catalog.serializers import ProductListSerializer

from .models import Coupon, Promotion


class CouponApplySerializer(serializers.Serializer):
    code = serializers.CharField()


class PromotionSerializer(serializers.ModelSerializer):
    products = ProductListSerializer(many=True, read_only=True)

    class Meta:
        model = Promotion
        fields = ["id", "name", "slug", "description", "products"]

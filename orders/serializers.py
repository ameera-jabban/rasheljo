from rest_framework import serializers

from accounts.serializers import AddressSerializer
from shipping.serializers import ShippingMethodSerializer

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "line_total"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "changed_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = AddressSerializer(read_only=True)
    shipping_method = ShippingMethodSerializer(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "status", "shipping_address", "shipping_method", "payment_method",
            "coupon_code", "discount_amount", "shipping_cost", "subtotal", "total",
            "items", "status_history", "created_at",
        ]
        read_only_fields = ["status", "subtotal", "total"]

from rest_framework import serializers

from orders.models import OrderItem

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    is_verified_purchase = serializers.BooleanField(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "user_name", "rating", "title", "body", "is_verified_purchase", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_user_name(self, obj):
        return obj.user.first_name or obj.user.email.split("@")[0]


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["product", "rating", "title", "body"]

    def validate(self, attrs):
        user = self.context["request"].user
        if Review.objects.filter(user=user, product=attrs["product"]).exists():
            raise serializers.ValidationError("You have already reviewed this product.")
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        # Auto-link to a delivered order item if one exists, for the verified-purchase badge.
        order_item = (
            OrderItem.objects.filter(order__user=user, order__status="delivered", product=validated_data["product"])
            .order_by("-order__created_at")
            .first()
        )
        return Review.objects.create(user=user, order_item=order_item, **validated_data)

from rest_framework import serializers

from .models import ShippingMethod


class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = ["id", "name_en", "name_ar", "cost", "estimated_days_min", "estimated_days_max"]

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ShippingMethod, ShippingZone


@admin.register(ShippingMethod)
class ShippingMethodAdmin(ModelAdmin):
    list_display = ("name_en", "cost", "estimated_days_min", "estimated_days_max", "is_active")
    search_fields = ("name_en", "name_ar")  # autocomplete source for OrderAdmin


@admin.register(ShippingZone)
class ShippingZoneAdmin(ModelAdmin):
    list_display = ("city", "method", "cost_override")
    list_select_related = ("method",)  # `method` column was 1 query/row
    search_fields = ("city",)

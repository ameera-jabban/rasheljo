from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Coupon, Promotion


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "times_used", "max_uses", "is_active")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code",)


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_active", "starts_at", "ends_at")
    # filter_horizontal rendered every one of the ~460 products as an <option>
    # (twice) on each change page; autocomplete fetches on demand instead.
    autocomplete_fields = ("products",)
    prepopulated_fields = {"slug": ("name",)}

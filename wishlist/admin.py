from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import WishlistItem


@admin.register(WishlistItem)
class WishlistItemAdmin(ModelAdmin):
    list_display = ("user", "product", "added_at")
    list_select_related = ("user", "product")  # both columns + __str__ were 2 queries/row
    list_filter = ("added_at",)
    search_fields = ("user__email", "product__name_en", "product__sku")
    autocomplete_fields = ("user", "product")

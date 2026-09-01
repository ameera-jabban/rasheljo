from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Review


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "created_at")
    list_select_related = ("product", "user")  # both columns + __str__ were 2 queries/row
    list_filter = ("rating", "is_approved")
    search_fields = ("product__name_en", "product__sku", "user__email")
    autocomplete_fields = ("product", "user")
    actions = ["approve_reviews", "reject_reviews"]

    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
    approve_reviews.short_description = "Approve selected reviews"

    def reject_reviews(self, request, queryset):
        queryset.update(is_approved=False)
    reject_reviews.short_description = "Reject selected reviews"

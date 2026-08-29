from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import HomepageVideo, Policy, SiteSettings


@admin.register(Policy)
class PolicyAdmin(ModelAdmin):
    list_display = ("slug", "title_en", "is_active", "updated_at")
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("slug", "title_en", "title_ar", "body_en", "body_ar")
    readonly_fields = ("updated_at",)
    prepopulated_fields = {"slug": ("title_en",)}


@admin.register(HomepageVideo)
class HomepageVideoAdmin(ModelAdmin):
    list_display = ("slot", "title_en", "is_active", "sort_order", "updated_at")
    list_filter = ("slot", "is_active")
    list_editable = ("is_active", "sort_order")
    search_fields = ("title_en", "title_ar", "video_url")


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    """Singleton — the React admin panel is the real UI. Lock down add/delete so
    Django admin can only ever edit the one row."""

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

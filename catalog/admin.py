from django.contrib import admin
from django.db import models
from django.forms import CheckboxSelectMultiple
from unfold.admin import ModelAdmin, TabularInline

from admin_reports.views import LOW_STOCK_THRESHOLD

from .models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant


class StockLevelFilter(admin.SimpleListFilter):
    """Sidebar filter + the target of the admin dashboard's low/out-of-stock
    links (``?stock_level=low`` / ``?stock_level=out``). Threshold is the same
    LOW_STOCK_THRESHOLD the reports use."""

    title = "stock level"
    parameter_name = "stock_level"

    def lookups(self, request, model_admin):
        return [
            ("out", "Out of stock (0)"),
            ("low", f"Low (1–{LOW_STOCK_THRESHOLD - 1})"),
            ("in", f"In stock ({LOW_STOCK_THRESHOLD}+)"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "out":
            return queryset.filter(stock=0)
        if value == "low":
            return queryset.filter(stock__gt=0, stock__lt=LOW_STOCK_THRESHOLD)
        if value == "in":
            return queryset.filter(stock__gte=LOW_STOCK_THRESHOLD)
        return queryset


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("sku", "name_en", "brand", "category", "price", "sale_price", "stock", "badge_type", "is_active", "ar_machine_translated")
    list_filter = ("brand", "category", "badge_type", "is_active", "ar_machine_translated", StockLevelFilter)
    search_fields = ("sku", "name_en", "name_ar")
    inlines = [ProductImageInline, ProductVariantInline]
    prepopulated_fields = {"slug": ("name_en",)}
    # Render the `attributes` M2M as a checkbox list rather than a <select multiple>.
    # django-unfold 0.104's themed multi-select widget makes its own bundled Alpine
    # throw during init on the product change form when the field has selected
    # values, blanking the page (x-cloak never clears). A plain widget sidesteps it,
    # and a checkbox list is the better UX for ~20 skin-type/concern attributes anyway.
    formfield_overrides = {models.ManyToManyField: {"widget": CheckboxSelectMultiple}}


@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ("name_en", "name_ar", "slug", "is_active", "ar_machine_translated")
    list_filter = ("is_active", "ar_machine_translated")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name_en", "name_ar", "slug", "parent", "is_active", "ar_machine_translated")
    list_filter = ("is_active", "ar_machine_translated", "parent")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(ProductAttribute)
class ProductAttributeAdmin(ModelAdmin):
    list_display = ("attribute_type", "value_en", "value_ar", "slug", "ar_machine_translated")
    list_filter = ("attribute_type", "ar_machine_translated")
    search_fields = ("value_en", "value_ar", "slug")

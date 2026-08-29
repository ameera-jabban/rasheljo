from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("sku", "name_en", "brand", "category", "price", "sale_price", "stock", "badge_type", "is_active", "ar_machine_translated")
    list_filter = ("brand", "category", "badge_type", "is_active", "ar_machine_translated")
    search_fields = ("sku", "name_en", "name_ar")
    inlines = [ProductImageInline, ProductVariantInline]
    prepopulated_fields = {"slug": ("name_en",)}


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

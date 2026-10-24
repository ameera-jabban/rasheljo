from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("product",)  # was a <select> of all 460 products per row


class OrderStatusHistoryInline(TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_at")


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ("id", "user", "customer_phone", "status", "total", "created_at")
    list_select_related = ("user", "shipping_address")  # `user` column was 1 query/row
    list_filter = ("status", "payment_method")
    search_fields = (
        "id", "user__email", "user__first_name", "user__last_name",
        "email", "shipping_address__name", "shipping_address__phone",
    )
    autocomplete_fields = ("user", "shipping_address", "shipping_method")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    @admin.display(description="Phone", ordering="shipping_address__phone")
    def customer_phone(self, obj):
        # guest orders have no user — the phone on the delivery address is how you reach them
        return obj.shipping_address.phone if obj.shipping_address_id else "—"

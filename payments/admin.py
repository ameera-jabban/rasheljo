from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Payment, PaymentAttempt


class PaymentAttemptInline(TabularInline):
    model = PaymentAttempt
    extra = 0
    readonly_fields = ("success", "raw_response", "created_at")


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ("order", "method", "status", "amount", "created_at")
    list_select_related = ("order",)  # `order` column was 1 query/row
    list_filter = ("method", "status")
    search_fields = ("order__id", "provider_reference", "idempotency_key")
    autocomplete_fields = ("order",)
    inlines = [PaymentAttemptInline]

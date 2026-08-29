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
    list_filter = ("method", "status")
    inlines = [PaymentAttemptInline]

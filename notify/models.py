from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPES = [
        ("order_confirmation", "Order Confirmation"),
        ("order_status_update", "Order Status Update"),
        ("password_reset", "Password Reset"),
        ("welcome", "Welcome"),
        ("low_stock", "Low Stock Alert"),
        ("review_request", "Review Request"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=TYPES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

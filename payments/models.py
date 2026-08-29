from django.db import models

from orders.models import Order


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("authorized", "Authorized"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    method = models.CharField(max_length=10, choices=Order.PAYMENT_METHODS)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    provider_reference = models.CharField(max_length=120, blank=True)
    # Idempotency key the client sends on payment initiation — prevents a
    # double-tapped "Pay" button or a retried request from creating two
    # charge attempts against the same gateway intent.
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["idempotency_key"])]

    def __str__(self):
        return f"Payment for Order #{self.order_id} ({self.status})"


class PaymentAttempt(models.Model):
    """Append-only log — every gateway call/response gets a row, so a failed
    card attempt doesn't just disappear if the customer retries."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="attempts")
    success = models.BooleanField()
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentWebhookEvent(models.Model):
    """Every inbound webhook call is logged verbatim before any processing —
    if signature verification or processing fails, the raw event is still on
    disk for replay/debugging rather than silently dropped."""

    provider = models.CharField(max_length=40)
    event_type = models.CharField(max_length=80, blank=True)
    payload = models.JSONField(default=dict)
    signature_valid = models.BooleanField(null=True)
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

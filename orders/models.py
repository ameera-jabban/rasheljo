from django.conf import settings
from django.db import models

from accounts.models import Address
from catalog.models import Product


class Order(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    PAYMENT_METHODS = [("cod", "Cash on Delivery"), ("card", "Card")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    shipping_address = models.ForeignKey(Address, on_delete=models.PROTECT, null=True, blank=True)
    shipping_method = models.ForeignKey(
        "shipping.ShippingMethod", on_delete=models.PROTECT, null=True, blank=True
    )
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default="cod")
    coupon_code = models.CharField(max_length=40, blank=True)
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # admin list_filter + date_hierarchy, admin_reports (orders-by-status,
            # sales-over-time), and the storefront order history all filter/sort
            # on these; unindexed today.
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    ALLOWED_TRANSITIONS = {
        "draft": {"pending", "cancelled"},
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"shipped", "cancelled"},
        "shipped": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }

    def transition_to(self, new_status):
        """Enforces the state machine from Part 3 instead of allowing an
        arbitrary status write from anywhere in the codebase."""
        if new_status not in self.ALLOWED_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Cannot transition order from '{self.status}' to '{new_status}'.")
        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        OrderStatusHistory.objects.create(order=self, from_status=old_status, to_status=new_status)

    def recalculate_totals(self):
        self.subtotal = sum((item.line_total for item in self.items.all()), start=0)
        self.shipping_cost = self.shipping_method.cost if self.shipping_method_id else 0
        self.total = self.subtotal + self.shipping_cost - self.discount_amount
        self.save(update_fields=["subtotal", "shipping_cost", "total", "updated_at"])

    def __str__(self):
        return f"Order #{self.id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)  # snapshot at purchase time
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, related_name="status_history", on_delete=models.CASCADE)
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]
        verbose_name_plural = "order status histories"

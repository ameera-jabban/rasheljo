from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from catalog.models import Product


class Coupon(models.Model):
    DISCOUNT_TYPES = [("percent", "Percentage"), ("fixed", "Fixed Amount")]

    code = models.CharField(max_length=40, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default="percent")
    discount_value = models.DecimalField(max_digits=8, decimal_places=2)
    min_order_value = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited")
    times_used = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code

    def is_valid_now(self):
        now = timezone.now()
        if not self.is_active:
            return False, "This coupon is no longer active."
        if now < self.valid_from:
            return False, "This coupon is not active yet."
        if self.valid_until and now > self.valid_until:
            return False, "This coupon has expired."
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False, "This coupon has reached its usage limit."
        return True, ""

    def calculate_discount(self, subtotal):
        if subtotal < self.min_order_value:
            return 0
        if self.discount_type == "percent":
            return round(subtotal * (self.discount_value / 100), 2)
        return min(self.discount_value, subtotal)


class Promotion(models.Model):
    """Backs the Hot Offers / Last Chance / Bestseller rails as explicit,
    manageable data instead of hardcoded homepage querysets — per Part 3's note
    that this was presentation-only logic on the old site."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    products = models.ManyToManyField(Product, related_name="promotions", blank=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

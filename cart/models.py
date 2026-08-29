from django.conf import settings
from django.db import models

from catalog.models import Product, ProductVariant


class Cart(models.Model):
    """One cart per logged-in user, or per anonymous session key for guests."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="cart"
    )
    session_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    coupon_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.all()), start=0)

    def __str__(self):
        owner = self.user.email if self.user_id else f"guest:{self.session_key}"
        return f"Cart({owner})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "product", "variant")

    @property
    def unit_price(self):
        price = self.product.current_price
        if self.variant:
            price += self.variant.price_delta
        return price

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.sku}"

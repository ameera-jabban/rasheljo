from django.conf import settings
from django.db import models

from catalog.models import Product


class WishlistItem(models.Model):
    """Deliberately separate from Cart per Part 2's architecture note: wishlist
    never expires and has different access patterns than a cart."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.user} ♥ {self.product.sku}"

from django.db import models


class ShippingMethod(models.Model):
    """Flat-rate by name for now — Jordan-only scope per Part 2's note not to
    over-engineer multi-country zones this catalog doesn't need yet."""

    name_en = models.CharField(max_length=80)
    name_ar = models.CharField(max_length=80, blank=True)
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["cost"]

    def __str__(self):
        return f"{self.name_en} ({self.cost} JOD)"


class ShippingZone(models.Model):
    """City-level override — e.g. Amman flat rate vs. outside-Amman rate."""

    city = models.CharField(max_length=80, unique=True)
    method = models.ForeignKey(ShippingMethod, on_delete=models.CASCADE, related_name="zones")
    cost_override = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.city

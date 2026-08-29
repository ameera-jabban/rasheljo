from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: adds phone + preferred language on top of Django's auth base."""

    phone = models.CharField(max_length=20, blank=True)
    preferred_language = models.CharField(
        max_length=2,
        choices=[("en", "English"), ("ar", "Arabic")],
        default="en",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email or self.username


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    city = models.CharField(max_length=80)
    area = models.CharField(max_length=120, blank=True)
    address_line = models.CharField(max_length=255)
    building = models.CharField(max_length=60, blank=True)
    apartment = models.CharField(max_length=60, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.name} — {self.city}"

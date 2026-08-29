from django.db import models
from django.utils.text import slugify


class Brand(models.Model):
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(unique=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True)
    banner = models.ImageField(upload_to="brands/banners/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    ar_machine_translated = models.BooleanField(
        default=False,
        help_text="Arabic name/description was machine-translated — review before treating as final.",
    )

    class Meta:
        ordering = ["name_en"]

    def __str__(self):
        return self.name_en

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en)
        super().save(*args, **kwargs)


class Category(models.Model):
    """Self-referencing so Series -> Sub-series works without a second model."""

    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    ar_machine_translated = models.BooleanField(
        default=False,
        help_text="Arabic name/description was machine-translated — review before treating as final.",
    )

    class Meta:
        ordering = ["name_en"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_en

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en)
        super().save(*args, **kwargs)


class ProductAttribute(models.Model):
    """Covers skin_type, concern, ingredient, texture via one table + a type enum,
    matching Part 2's schema decision (one table, not four)."""

    ATTRIBUTE_TYPES = [
        ("skin_type", "Skin Type"),
        ("concern", "Concern"),
        ("ingredient", "Ingredient"),
        ("texture", "Texture"),
    ]
    attribute_type = models.CharField(max_length=20, choices=ATTRIBUTE_TYPES)
    value_en = models.CharField(max_length=80)
    value_ar = models.CharField(max_length=80, blank=True)
    slug = models.SlugField()
    ar_machine_translated = models.BooleanField(
        default=False,
        help_text="Arabic value was machine-translated — review before treating as final.",
    )

    class Meta:
        unique_together = ("attribute_type", "slug")
        ordering = ["attribute_type", "value_en"]

    def __str__(self):
        return f"{self.get_attribute_type_display()}: {self.value_en}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.value_en)
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    def with_ratings(self):
        """Attach `average_rating` (float | None) and `review_count` (int) from
        *approved* reviews as a single filtered aggregate — no per-row query.
        Opt-in (not applied by default) so plain `.update()` / bulk paths and
        other aggregations stay unaffected."""
        from django.db.models import Avg, Count, Q

        return self.annotate(
            average_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
            review_count=Count("reviews", filter=Q(reviews__is_approved=True), distinct=True),
        )


class Product(models.Model):
    objects = ProductQuerySet.as_manager()

    BADGE_CHOICES = [
        ("bestseller", "Bestseller"),
        ("new_arrival", "New Arrival"),
        ("hot_offer", "Hot Offer"),
        ("last_chance", "Last Chance"),
        ("set", "Set / Bundle"),
    ]

    sku = models.CharField(max_length=40, unique=True)
    name_en = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(unique=True, max_length=220)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    benefits_en = models.TextField(
        blank=True, help_text="One benefit per line — matches the live site's Benefits (EN) bullet list."
    )
    benefits_ar = models.TextField(blank=True, help_text="One benefit per line — matches الفوائد (AR).")
    how_to_use_en = models.TextField(blank=True)
    how_to_use_ar = models.TextField(blank=True)

    brand = models.ForeignKey(Brand, related_name="products", on_delete=models.PROTECT)
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.PROTECT, null=True, blank=True
    )
    attributes = models.ManyToManyField(ProductAttribute, related_name="products", blank=True)

    price = models.DecimalField(max_digits=8, decimal_places=2)
    sale_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    pack_size = models.CharField(max_length=40, blank=True, help_text='e.g. "3 PCS", "10-Piece Set"')

    badge_type = models.CharField(max_length=20, choices=BADGE_CHOICES, blank=True)
    is_active = models.BooleanField(default=True)
    ar_machine_translated = models.BooleanField(
        default=False,
        help_text="Arabic name/description was machine-translated — review before treating as final.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["sku"]),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name_en}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en)[:220]
        super().save(*args, **kwargs)

    @property
    def current_price(self):
        return self.sale_price if self.sale_price is not None else self.price

    @property
    def is_on_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def discount_percent(self):
        if not self.is_on_sale:
            return 0
        return round((1 - (self.sale_price / self.price)) * 100)

    @property
    def in_stock(self):
        return self.stock > 0

    def benefits_list(self, lang="en"):
        """Splits the newline-separated benefits field into a real list —
        mirrors the live site's bullet-point Benefits (EN)/الفوائد (AR) block."""
        raw = self.benefits_ar if lang == "ar" else self.benefits_en
        return [line.strip() for line in raw.splitlines() if line.strip()]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/")
    sort_order = models.PositiveIntegerField(default=0)
    alt_text_en = models.CharField(max_length=200, blank=True)
    alt_text_ar = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"Image for {self.product.sku} (#{self.sort_order})"


class ProductVariant(models.Model):
    """Placeholder for future size/color/volume variants — not all products need one."""

    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name_en = models.CharField(max_length=80)
    name_ar = models.CharField(max_length=80, blank=True)
    sku_suffix = models.CharField(max_length=20, blank=True)
    price_delta = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.sku} / {self.name_en}"

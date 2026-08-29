from django.core.exceptions import ValidationError
from django.db import models


class Policy(models.Model):
    """A static legal / info page (privacy, terms, returns, shipping) that a store
    admin edits without a deploy. Slugs are stable so footer links never break;
    body text is plain text — paragraphs separated by blank lines, rendered with
    line breaks on the storefront (deliberately no rich-text editor)."""

    PRIVACY = "privacy-policy"
    TERMS = "terms-conditions"
    RETURNS = "return-policy"
    SHIPPING = "shipping-policy"

    # (slug, default English title) — used by the data migration to seed the rows.
    DEFAULTS = [
        (PRIVACY, "Privacy Policy"),
        (TERMS, "Terms & Conditions"),
        (RETURNS, "Return Policy"),
        (SHIPPING, "Shipping Policy"),
    ]

    slug = models.SlugField(unique=True)
    title_en = models.CharField(max_length=200)
    title_ar = models.CharField(max_length=200, blank=True)
    body_en = models.TextField(blank=True)
    body_ar = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        verbose_name = "policy"
        verbose_name_plural = "policies"

    def __str__(self):
        return self.title_en or self.slug


class SiteSettings(models.Model):
    """Singleton — global storefront chrome (footer, social links, store map) that
    a store admin edits without a deploy. Always pk=1; use SiteSettings.load()."""

    site_name = models.CharField(max_length=120, default="Dr Rashel Jo")
    logo = models.ImageField(upload_to="site/", blank=True, null=True)

    about_text_en = models.TextField(blank=True)
    about_text_ar = models.TextField(blank=True)

    instagram_url = models.URLField(blank=True)
    whatsapp_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    map_embed_url = models.URLField(
        blank=True, max_length=1000,
        help_text="Google Maps embed iframe src (the one from Share → Embed a map).",
    )
    map_open_url = models.URLField(
        blank=True, max_length=1000,
        help_text='Plain maps.google.com link for the "Open in Maps" button.',
    )

    copyright_text_en = models.CharField(
        max_length=300, blank=True,
        help_text="Leave blank to auto-generate from site_name and the current year.",
    )
    copyright_text_ar = models.CharField(max_length=300, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1  # collapse every write onto the one row
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # the singleton is never deleted

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HomepageVideo(models.Model):
    """A single video slot on the storefront homepage — the hero background video
    plus the shorter promo videos between merchandising rails. Store admins add /
    replace / reorder these without a code deploy, matching the design doc's
    "content — CMS-lite for homepage banner slots" note."""

    HERO = "hero"
    SECTION_1 = "section_1"
    SECTION_2 = "section_2"
    SECTION_3 = "section_3"
    SLOT_CHOICES = [
        (HERO, "Hero (top of page)"),
        (SECTION_1, "Section 1 (between rails)"),
        (SECTION_2, "Section 2 (between rails)"),
        (SECTION_3, "Section 3 (between rails)"),
    ]

    slot = models.CharField(
        max_length=32,
        choices=SLOT_CHOICES,
        help_text="Which homepage position this video fills.",
    )
    video_file = models.FileField(
        upload_to="homepage/videos/",
        blank=True,
        help_text="Upload a video file, OR set an external video URL below — not both.",
    )
    video_url = models.URLField(
        blank=True,
        help_text="External (e.g. CDN-hosted) video URL, as an alternative to uploading a file.",
    )
    poster_image = models.ImageField(
        upload_to="homepage/posters/",
        blank=True,
        null=True,
        help_text="Shown while the video loads or if autoplay is blocked.",
    )

    title_en = models.CharField(max_length=200, blank=True)
    title_ar = models.CharField(max_length=200, blank=True)
    subtitle_en = models.CharField(max_length=300, blank=True)
    subtitle_ar = models.CharField(max_length=300, blank=True)

    link_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="Where clicking the video / banner navigates (relative or absolute).",
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slot", "sort_order"]

    def __str__(self):
        return f"{self.get_slot_display()} — {self.title_en or self.video_url or self.video_file.name or '(empty)'}"

    def clean(self):
        """An active slot must resolve to exactly one playable source. Inactive
        rows are drafts and skip the check so an admin can save work in progress."""
        if not self.is_active:
            return
        has_file = bool(self.video_file)
        has_url = bool(self.video_url)
        if has_file and has_url:
            raise ValidationError(
                "Set either an uploaded video file or an external video URL, not both."
            )
        if not has_file and not has_url:
            raise ValidationError(
                "An active homepage video needs either an uploaded video file or an external video URL."
            )

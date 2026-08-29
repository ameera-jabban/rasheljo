from rest_framework import serializers

from .models import HomepageVideo, Policy, SiteSettings


class PolicySummarySerializer(serializers.ModelSerializer):
    """Slim shape for a footer / policy index — no body text."""

    class Meta:
        model = Policy
        fields = ["slug", "title_en", "title_ar"]


class PolicySerializer(serializers.ModelSerializer):
    """Full public policy page — shared read shape for the storefront detail view."""

    class Meta:
        model = Policy
        fields = ["slug", "title_en", "title_ar", "body_en", "body_ar", "updated_at"]
        read_only_fields = fields


class HomepageVideoSerializer(serializers.ModelSerializer):
    """Public, read-only shape for the storefront homepage. `video_src` collapses
    the file-or-URL choice so the frontend never has to branch on which one is set."""

    video_src = serializers.SerializerMethodField()

    class Meta:
        model = HomepageVideo
        fields = [
            "id",
            "slot",
            "video_file",
            "video_url",
            "video_src",
            "poster_image",
            "title_en",
            "title_ar",
            "subtitle_en",
            "subtitle_ar",
            "link_url",
            "sort_order",
        ]

    def get_video_src(self, obj):
        if obj.video_file:
            request = self.context.get("request")
            url = obj.video_file.url
            return request.build_absolute_uri(url) if request else url
        return obj.video_url or None


class SiteSettingsSerializer(serializers.ModelSerializer):
    """Shared by the public GET and the admin GET/PATCH. `logo` is a plain
    file field so multipart upload works the same way it does for product images."""

    class Meta:
        model = SiteSettings
        fields = [
            "site_name",
            "logo",
            "about_text_en",
            "about_text_ar",
            "instagram_url",
            "whatsapp_url",
            "facebook_url",
            "tiktok_url",
            "map_embed_url",
            "map_open_url",
            "copyright_text_en",
            "copyright_text_ar",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

from rest_framework import generics

from .models import HomepageVideo, Policy, SiteSettings
from .serializers import (
    HomepageVideoSerializer,
    PolicySerializer,
    PolicySummarySerializer,
    SiteSettingsSerializer,
)


class HomepageVideoListView(generics.ListAPIView):
    """GET /api/v1/homepage-videos/ — active homepage videos, ordered by slot then
    sort_order. Public (no auth), same as catalog's storefront endpoints."""

    queryset = HomepageVideo.objects.filter(is_active=True).order_by("slot", "sort_order")
    serializer_class = HomepageVideoSerializer
    pagination_class = None  # tiny fixed list (a handful of slots) — nothing to paginate


class SiteSettingsView(generics.RetrieveAPIView):
    """GET /api/v1/site-settings/ — the single SiteSettings object (never a list).
    Public, no auth. The row is auto-created on first access via SiteSettings.load()."""

    serializer_class = SiteSettingsSerializer

    def get_object(self):
        return SiteSettings.load()


class PolicyListView(generics.ListAPIView):
    """GET /api/v1/policies/ — active policies, slug + title only, for a footer /
    policy index. Public, no auth."""

    queryset = Policy.objects.filter(is_active=True)
    serializer_class = PolicySummarySerializer
    pagination_class = None  # a handful of fixed pages — nothing to paginate


class PolicyDetailView(generics.RetrieveAPIView):
    """GET /api/v1/policies/<slug>/ — full policy page. 404 if the slug is unknown
    or the policy is inactive. Public, no auth."""

    queryset = Policy.objects.filter(is_active=True)
    serializer_class = PolicySerializer
    lookup_field = "slug"

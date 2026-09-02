"""Cache invalidation for the storefront's shared (Redis) reference-data cache
(see storefront/services.py).

Without this, editing a HomepageVideo or SiteSettings in the Django Admin does
not change the storefront until the 60s TTL expires — `homepage_videos_by_slot()`
and `get_site_settings()` are served from the `sf:ref:*` cache. `services.invalidate`
does a `cache.delete`, so every gunicorn worker sees the eviction immediately.
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from content.models import HomepageVideo, SiteSettings
from storefront import services


@receiver([post_save, post_delete], sender=HomepageVideo, dispatch_uid="sf_homepage_video_cache")
def _clear_homepage_video_cache(**kwargs):
    services.invalidate("homepage_videos")


@receiver(post_save, sender=SiteSettings, dispatch_uid="sf_site_settings_cache")
def _clear_site_settings_cache(**kwargs):
    services.invalidate("site_settings")

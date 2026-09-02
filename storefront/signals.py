"""Cache invalidation for the storefront's shared (Redis) reference-data cache
(see storefront/services.py).

Every dataset `_cached()` in services.py under an `sf:ref:*` key has a
`post_save`/`post_delete` receiver here so a Django Admin edit shows up on the
storefront immediately instead of after the 60s TTL. `services.invalidate` does
a `cache.delete`, so every gunicorn worker sees the eviction at once.

    cache key            model(s)                    services.py function
    -------------------  --------------------------  ------------------------
    homepage_videos      content.HomepageVideo       homepage_videos_by_slot()
    site_settings        content.SiteSettings        get_site_settings()
    brands               catalog.Brand               brands()
    categories           catalog.Category            categories()
    skin_types           catalog.ProductAttribute*   skin_types()
    policies             content.Policy              active_policies()
    shipping_methods     shipping.ShippingMethod     shipping_methods()

* skin_types() only reads ProductAttribute rows with attribute_type="skin_type",
  but the receiver fires for every ProductAttribute write (concern / ingredient /
  texture too). Those are rare admin edits and the cost is a single extra query
  on the next request, so it's not worth inspecting the instance to narrow it.
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Brand, Category, ProductAttribute
from content.models import HomepageVideo, Policy, SiteSettings
from shipping.models import ShippingMethod
from storefront import services


@receiver([post_save, post_delete], sender=HomepageVideo, dispatch_uid="sf_homepage_video_cache")
def _clear_homepage_video_cache(**kwargs):
    services.invalidate("homepage_videos")


@receiver(post_save, sender=SiteSettings, dispatch_uid="sf_site_settings_cache")
def _clear_site_settings_cache(**kwargs):
    services.invalidate("site_settings")


@receiver([post_save, post_delete], sender=Brand, dispatch_uid="sf_brands_cache")
def _clear_brands_cache(**kwargs):
    services.invalidate("brands")


@receiver([post_save, post_delete], sender=Category, dispatch_uid="sf_categories_cache")
def _clear_categories_cache(**kwargs):
    services.invalidate("categories")


@receiver([post_save, post_delete], sender=ProductAttribute, dispatch_uid="sf_skin_types_cache")
def _clear_skin_types_cache(**kwargs):
    services.invalidate("skin_types")


@receiver([post_save, post_delete], sender=Policy, dispatch_uid="sf_policies_cache")
def _clear_policies_cache(**kwargs):
    services.invalidate("policies")


@receiver([post_save, post_delete], sender=ShippingMethod, dispatch_uid="sf_shipping_methods_cache")
def _clear_shipping_methods_cache(**kwargs):
    services.invalidate("shipping_methods")

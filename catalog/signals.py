"""Invalidate the storefront's Redis catalog cache (see storefront/services.py)
whenever catalog data an admin can edit changes.

Generation-based: one counter bump makes every cached rail / product-detail /
recommendation entry unreachable at once, so a store admin never has to wait out
the 5-minute TTL after editing a price, stock level, badge, image or brand.
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Brand, Category, Product, ProductImage
from storefront import services


@receiver([post_save, post_delete], sender=Product, dispatch_uid="sf_catbump_product")
@receiver([post_save, post_delete], sender=ProductImage, dispatch_uid="sf_catbump_image")
@receiver([post_save, post_delete], sender=Brand, dispatch_uid="sf_catbump_brand")
@receiver([post_save, post_delete], sender=Category, dispatch_uid="sf_catbump_category")
def _invalidate_catalog_cache(**kwargs):
    services.bump_catalog_gen()

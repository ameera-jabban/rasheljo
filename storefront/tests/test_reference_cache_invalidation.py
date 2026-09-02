"""Admin edits to the storefront's cached reference data must evict the shared
`sf:ref:*` cache immediately (not wait out the 60s TTL) — same pattern as
test_homepage_video_cache.py, for the five datasets wired up later:
brands, categories, skin_types, policies, shipping_methods.

See storefront/signals.py. Assertions are membership / eviction based rather
than exact counts, because the test DB carries migration-seeded Policy rows.
"""
import pytest
from django.core.cache import cache

from catalog.models import ProductAttribute
from catalog.tests.factories import BrandFactory, CategoryFactory, ProductAttributeFactory
from content.models import Policy
from shipping.models import ShippingMethod
from storefront import services

pytestmark = pytest.mark.django_db


class TestBrandsInvalidation:
    def test_save_evicts_and_next_read_is_fresh(self):
        BrandFactory(name_en="Alpha Brand", is_active=True)
        names = {b.name_en for b in services.brands()}
        assert "Alpha Brand" in names
        assert cache.get("sf:ref:brands") is not None

        BrandFactory(name_en="Beta Brand", is_active=True)
        assert cache.get("sf:ref:brands") is None
        assert {"Alpha Brand", "Beta Brand"} <= {b.name_en for b in services.brands()}

    def test_delete_evicts(self):
        b = BrandFactory(is_active=True)
        services.brands()
        b.delete()
        assert cache.get("sf:ref:brands") is None


class TestCategoriesInvalidation:
    def test_save_evicts(self):
        CategoryFactory(name_en="Serums Cat", is_active=True)
        services.categories()
        assert cache.get("sf:ref:categories") is not None
        CategoryFactory(name_en="Masks Cat", is_active=True)
        assert cache.get("sf:ref:categories") is None
        assert "Masks Cat" in {c.name_en for c in services.categories()}

    def test_reparenting_a_category_evicts(self):
        parent = CategoryFactory(is_active=True)
        child = CategoryFactory(is_active=True)
        services.categories()
        child.parent = parent
        child.save()
        assert cache.get("sf:ref:categories") is None


class TestSkinTypesInvalidation:
    def test_skin_type_save_evicts_and_next_read_is_fresh(self):
        ProductAttributeFactory(attribute_type="skin_type", value_en="Dry Skin")
        assert "Dry Skin" in {s.value_en for s in services.skin_types()}
        ProductAttributeFactory(attribute_type="skin_type", value_en="Oily Skin")
        assert cache.get("sf:ref:skin_types") is None
        assert {"Dry Skin", "Oily Skin"} <= {s.value_en for s in services.skin_types()}

    def test_non_skin_type_attribute_also_evicts(self):
        # Documented over-broad behaviour: skin_types() only reads
        # attribute_type="skin_type", but the receiver fires for every
        # ProductAttribute. Harmless (one extra query next request).
        services.skin_types()
        ProductAttribute.objects.create(attribute_type="concern", value_en="Acne", slug="acne")
        assert cache.get("sf:ref:skin_types") is None

    def test_delete_evicts(self):
        attr = ProductAttributeFactory(attribute_type="skin_type")
        services.skin_types()
        attr.delete()
        assert cache.get("sf:ref:skin_types") is None


class TestPoliciesInvalidation:
    def test_save_evicts_and_new_policy_is_visible(self):
        services.active_policies()
        assert cache.get("sf:ref:policies") is not None
        Policy.objects.create(slug="cookie-policy", title_en="Cookies", is_active=True)
        assert cache.get("sf:ref:policies") is None
        assert "cookie-policy" in {p.slug for p in services.active_policies()}

    def test_deactivating_a_policy_is_reflected_immediately(self):
        p = Policy.objects.create(slug="temp-policy", title_en="Temp", is_active=True)
        assert "temp-policy" in {x.slug for x in services.active_policies()}
        p.is_active = False
        p.save()
        assert "temp-policy" not in {x.slug for x in services.active_policies()}

    def test_delete_evicts(self):
        p = Policy.objects.create(slug="gone-policy", title_en="Gone")
        services.active_policies()
        p.delete()
        assert cache.get("sf:ref:policies") is None


class TestShippingMethodsInvalidation:
    def test_save_evicts_and_next_read_is_fresh(self):
        ShippingMethod.objects.create(name_en="Standard Ship", cost="2.00", is_active=True)
        assert "Standard Ship" in {m.name_en for m in services.shipping_methods()}
        ShippingMethod.objects.create(name_en="Express Ship", cost="5.00", is_active=True)
        assert cache.get("sf:ref:shipping_methods") is None
        assert {"Standard Ship", "Express Ship"} <= {m.name_en for m in services.shipping_methods()}

    def test_deactivating_a_method_is_reflected_immediately(self):
        m = ShippingMethod.objects.create(name_en="Courier Ship", cost="9.00", is_active=True)
        assert "Courier Ship" in {x.name_en for x in services.shipping_methods()}
        m.is_active = False
        m.save()
        assert "Courier Ship" not in {x.name_en for x in services.shipping_methods()}

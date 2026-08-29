import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


class TestRecommendations:
    def test_recommends_same_category_first(self):
        cat = CategoryFactory()
        p1 = ProductFactory(category=cat)
        p2 = ProductFactory(category=cat)
        ProductFactory()  # different category, shouldn't crowd out same-category matches

        resp = APIClient().get(reverse("product-recommendations", kwargs={"slug": p1.slug}))
        skus = [p["sku"] for p in resp.data]
        assert p2.sku in skus
        assert p1.sku not in skus  # never recommends itself

    def test_falls_back_to_brand_when_no_category_match(self):
        from catalog.tests.factories import BrandFactory
        brand = BrandFactory()
        p1 = ProductFactory(brand=brand, category=None)
        p2 = ProductFactory(brand=brand, category=None)

        resp = APIClient().get(reverse("product-recommendations", kwargs={"slug": p1.slug}))
        skus = [p["sku"] for p in resp.data]
        assert p2.sku in skus

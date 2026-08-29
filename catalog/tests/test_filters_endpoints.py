import pytest
from django.urls import reverse

from catalog.models import Category, ProductAttribute
from catalog.tests.factories import BrandFactory

pytestmark = pytest.mark.django_db


class TestSkinTypeListEndpoint:
    def test_lists_only_skin_type_attributes_without_auth(self, client):
        ProductAttribute.objects.create(attribute_type="skin_type", value_en="Oily Skin", slug="oily-skin")
        ProductAttribute.objects.create(attribute_type="skin_type", value_en="Dry Skin", slug="dry-skin")
        ProductAttribute.objects.create(attribute_type="concern", value_en="Acne", slug="acne")

        resp = client.get(reverse("skin-type-list"))
        assert resp.status_code == 200
        slugs = {row["slug"] for row in resp.data}
        assert slugs == {"oily-skin", "dry-skin"}
        assert all(row["attribute_type"] == "skin_type" for row in resp.data)

    def test_not_paginated(self, client):
        for i in range(30):
            ProductAttribute.objects.create(
                attribute_type="skin_type", value_en=f"Type {i}", slug=f"type-{i}"
            )
        resp = client.get(reverse("skin-type-list"))
        assert isinstance(resp.data, list)
        assert len(resp.data) == 30


class TestCategoryListNotTruncated:
    def test_returns_every_active_category_unpaginated(self, client):
        for i in range(40):
            Category.objects.create(name_en=f"Cat {i}", slug=f"cat-{i}", is_active=True)
        Category.objects.create(name_en="Hidden", slug="hidden", is_active=False)

        resp = client.get(reverse("category-list"))
        assert isinstance(resp.data, list)  # not a {count, results} page
        assert len(resp.data) == 40


class TestBrandListNotPaginated:
    def test_returns_bare_list(self, client):
        BrandFactory(slug="a")
        BrandFactory(slug="b")
        resp = client.get(reverse("brand-list"))
        assert isinstance(resp.data, list)
        assert len(resp.data) == 2

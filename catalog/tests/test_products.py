import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import BrandFactory, CategoryFactory, ProductAttributeFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


class TestProductList:
    def test_lists_only_active_products(self, client):
        ProductFactory(is_active=True)
        ProductFactory(is_active=False)
        resp = client.get(reverse("product-list"))
        assert resp.status_code == 200
        assert resp.data["count"] == 1

    def test_filters_by_brand_slug(self, client):
        dr_rashel = BrandFactory(slug="dr-rashel")
        estelin = BrandFactory(slug="estelin")
        ProductFactory(brand=dr_rashel)
        ProductFactory(brand=estelin)

        resp = client.get(reverse("product-list"), {"brand": "estelin"})
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["brand"]["slug"] == "estelin"

    def test_filters_by_badge_type(self, client):
        ProductFactory(badge_type="hot_offer")
        ProductFactory(badge_type="bestseller")
        resp = client.get(reverse("product-list"), {"badge": "hot_offer"})
        assert resp.data["count"] == 1

    def test_filters_by_skin_type_attribute(self, client):
        oily = ProductAttributeFactory(slug="oily-skin")
        p1 = ProductFactory()
        p1.attributes.add(oily)
        ProductFactory()  # no attribute

        resp = client.get(reverse("product-list"), {"skin_type": "oily-skin"})
        assert resp.data["count"] == 1

    def test_search_matches_name_and_sku(self, client):
        ProductFactory(sku="DRL-9999", name_en="Vitamin C Face Cream")
        ProductFactory(sku="DRL-1111", name_en="Aloe Vera Gel")

        resp = client.get(reverse("product-list"), {"search": "Vitamin"})
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["sku"] == "DRL-9999"

    def test_ordering_by_price(self, client):
        ProductFactory(price="20.00")
        ProductFactory(price="5.00")
        resp = client.get(reverse("product-list"), {"ordering": "price"})
        prices = [r["price"] for r in resp.data["results"]]
        assert prices == ["5.00", "20.00"]

    def test_sale_price_computes_discount_and_current_price(self, client):
        p = ProductFactory(price="10.00", sale_price="7.50")
        resp = client.get(reverse("product-detail", kwargs={"slug": p.slug}))
        assert resp.data["current_price"] == "7.50"
        assert resp.data["is_on_sale"] is True
        assert resp.data["discount_percent"] == 25

    def test_out_of_stock_flag(self, client):
        p = ProductFactory(stock=0)
        resp = client.get(reverse("product-detail", kwargs={"slug": p.slug}))
        assert resp.data["in_stock"] is False


class TestSearch:
    def test_combined_search_returns_products_categories_brands(self, client):
        BrandFactory(name_en="Vitamin Labs")
        CategoryFactory(name_en="Vitamin Collection")
        ProductFactory(name_en="Vitamin C Serum")

        resp = client.get(reverse("search"), {"q": "Vitamin"})
        assert len(resp.data["products"]) == 1
        assert len(resp.data["categories"]) == 1
        assert len(resp.data["brands"]) == 1

    def test_empty_query_returns_empty_results(self, client):
        resp = client.get(reverse("search"), {"q": ""})
        assert resp.data == {"products": [], "categories": [], "brands": []}

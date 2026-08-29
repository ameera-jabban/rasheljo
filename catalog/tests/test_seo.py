import pytest
from django.urls import reverse

from catalog.tests.factories import BrandFactory, CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db


class TestRobotsTxt:
    def test_served_as_plain_text_with_sitemap_reference(self, client):
        resp = client.get(reverse("robots-txt"))
        assert resp.status_code == 200
        assert resp["content-type"].startswith("text/plain")
        body = resp.content.decode()
        assert "User-agent: *" in body
        assert "Sitemap: https://dr-rasheljo.com/sitemap.xml" in body

    def test_disallows_private_and_api_paths(self, client):
        body = client.get(reverse("robots-txt")).content.decode()
        for path in ("/*/cart", "/*/checkout", "/*/account", "/*/search", "/api/"):
            assert f"Disallow: {path}" in body

    def test_does_not_block_product_or_category_paths(self, client):
        body = client.get(reverse("robots-txt")).content.decode()
        assert "Disallow: /*/products" not in body
        assert "Disallow: /*/category" not in body


class TestSitemapXml:
    def test_lists_active_products_in_both_languages(self, client):
        active = ProductFactory(is_active=True, slug="active-serum")
        ProductFactory(is_active=False, slug="hidden-serum")

        resp = client.get(reverse("sitemap-xml"))
        assert resp.status_code == 200
        assert resp["content-type"] == "application/xml"
        body = resp.content.decode()
        assert f"https://dr-rasheljo.com/en/products/{active.slug}" in body
        assert f"https://dr-rasheljo.com/ar/products/{active.slug}" in body
        assert "hidden-serum" not in body

    def test_includes_brands_categories_home_and_shop(self, client):
        brand = BrandFactory(slug="dr-rashel", is_active=True)
        category = CategoryFactory(slug="serums", is_active=True)

        body = client.get(reverse("sitemap-xml")).content.decode()
        assert "https://dr-rasheljo.com/en</loc>" in body
        assert "https://dr-rasheljo.com/en/shop</loc>" in body
        assert f"https://dr-rasheljo.com/en/brands/{brand.slug}" in body
        assert f"https://dr-rasheljo.com/en/category/{category.slug}" in body

    def test_every_url_has_hreflang_alternates(self, client):
        ProductFactory(is_active=True)
        body = client.get(reverse("sitemap-xml")).content.decode()
        assert 'hreflang="en"' in body
        assert 'hreflang="ar"' in body
        assert 'hreflang="x-default"' in body
        # one <loc> per <url>
        assert body.count("<loc>") == body.count("<url>")

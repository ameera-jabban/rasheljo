"""Redis (data-layer) caching of the storefront's hot catalog reads, and
generation-based invalidation on catalog writes. Uses the locmem cache from
config.settings_test_overrides."""
import pytest
from django.core.cache import cache
from django.urls import reverse

from catalog.models import Category, Product
from catalog.tests.factories import BrandFactory, ProductFactory
from storefront import services

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def brand():
    return BrandFactory(name_en="DR.RASHEL", slug="dr-rashel")


class TestRailCache:
    def test_rail_products_second_call_hits_no_db(self, django_assert_num_queries, brand):
        ProductFactory(brand=brand, badge_type="bestseller", stock=5)
        services.rail_products("bestseller")  # populate
        with django_assert_num_queries(0):
            services.rail_products("bestseller")

    def test_product_save_invalidates_rail(self, brand):
        p = ProductFactory(brand=brand, badge_type="bestseller", stock=5, price="5.00")
        assert [x.id for x in services.rail_products("bestseller")] == [p.id]

        p.price = "9.99"
        p.save()

        again = services.rail_products("bestseller")
        assert str(again[0].price) == "9.99"

    def test_new_product_appears_after_save(self, brand):
        ProductFactory(brand=brand, badge_type="bestseller", stock=5)
        assert len(services.rail_products("bestseller")) == 1
        ProductFactory(brand=brand, badge_type="bestseller", stock=5)
        assert len(services.rail_products("bestseller")) == 2


class TestProductDetailCache:
    def test_get_product_cached_then_invalidated_on_save(self, django_assert_num_queries, brand):
        p = ProductFactory(brand=brand, slug="serum-x", stock=5, price="10.00")
        services.get_product("serum-x")
        with django_assert_num_queries(0):
            services.get_product("serum-x")

        p.stock = 0
        p.save()
        assert services.get_product("serum-x").stock == 0

    def test_missing_slug_is_not_cached(self, brand):
        assert services.get_product("nope") is None
        ProductFactory(brand=brand, slug="nope", stock=1)
        assert services.get_product("nope") is not None


class TestShopLandingCache:
    def test_bare_category_landing_is_cached(self, django_assert_num_queries, brand):
        cat = Category.objects.create(name_en="Serum", slug="serum")
        ProductFactory(brand=brand, category=cat, stock=5)
        qp = {}
        services.shop_products(qp, landing="category", landing_slug="serum")
        with django_assert_num_queries(0):
            services.shop_products(qp, landing="category", landing_slug="serum")

    def test_filtered_request_is_not_cached(self, brand):
        cat = Category.objects.create(name_en="Serum", slug="serum")
        ProductFactory(brand=brand, category=cat, stock=5)
        qs, _ = services.shop_products({"ordering": "price"}, landing="category", landing_slug="serum")
        # a queryset, not a cached list
        assert not isinstance(qs, list)

    def test_page_still_renders_and_reflects_edit(self, client, brand):
        cat = Category.objects.create(name_en="Serum", slug="serum")
        p = ProductFactory(brand=brand, category=cat, stock=5, name_en="Alpha Serum")
        url = reverse("storefront:category", kwargs={"slug": "serum"})
        assert "Alpha Serum" in client.get(url).content.decode()

        p.name_en = "Renamed Serum"
        p.save()
        assert "Renamed Serum" in client.get(url).content.decode()


class TestGenerationCounter:
    def test_bump_changes_the_gen(self):
        g1 = services._catalog_gen()
        services.bump_catalog_gen()
        assert services._catalog_gen() == g1 + 1

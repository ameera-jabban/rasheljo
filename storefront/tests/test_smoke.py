"""Phase 1 smoke tests for the Django-templates storefront.

These assert the new presentation layer renders and its htmx cart endpoints
mutate the real Cart model — they do NOT re-test catalog/cart/orders logic,
which keeps its own suites.
"""
import pytest
from django.urls import reverse

from catalog.tests.factories import BrandFactory, ProductFactory
from cart.models import Cart, CartItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    return ProductFactory(brand=BrandFactory(name_en="DR.RASHEL", slug="dr-rashel"),
                          badge_type="bestseller", stock=10, price="8.80")


class TestPagesRender:
    @pytest.mark.parametrize("path", ["/en/", "/ar/", "/en/shop/", "/ar/shop/", "/en/skin-quiz/"])
    def test_200(self, client, path, product):
        assert client.get(path).status_code == 200

    def test_bare_root_redirects_to_en(self, client):
        r = client.get("/")
        assert r.status_code == 302 and r["Location"] == "/en/"

    def test_home_shows_bestseller_rail(self, client, product):
        html = client.get("/en/").content.decode()
        assert product.name_en in html
        assert "8.80" in html  # price formatting

    def test_arabic_is_rtl(self, client):
        html = client.get("/ar/").content.decode()
        assert 'dir="rtl"' in html
        assert 'lang="ar"' in html

    def test_language_switch_link_present(self, client):
        html = client.get("/en/").content.decode()
        assert "/ar/" in html  # header language toggle


class TestCartHtmx:
    def test_add_creates_cart_item_and_returns_stepper(self, client, product):
        r = client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        assert r.status_code == 200
        assert Cart.objects.count() == 1
        item = CartItem.objects.get()
        assert item.product == product and item.quantity == 1
        body = r.content.decode()
        assert 'cart-badge' in body and 'hx-swap-oob="true"' in body  # OOB badge swap
        assert r["HX-Trigger"]  # toast

    def test_update_quantity(self, client, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        item = CartItem.objects.get()
        client.post(reverse("storefront:cart_update", args=[item.id]), {"quantity": 3})
        item.refresh_from_db()
        assert item.quantity == 3

    def test_remove(self, client, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        item = CartItem.objects.get()
        client.post(reverse("storefront:cart_remove", args=[item.id]))
        assert not CartItem.objects.exists()

    def test_add_respects_stock(self, client):
        p = ProductFactory(stock=0, price="5.00", badge_type="hot_offer")
        client.post(reverse("storefront:cart_add"), {"product_id": p.id})
        assert not CartItem.objects.exists()


class TestWishlistHtmx:
    def test_toggle_requires_auth(self, client, product):
        assert client.post(reverse("storefront:wishlist_toggle", args=[product.id])).status_code == 401

    def test_toggle_adds_then_removes(self, django_user_model, client, product):
        user = django_user_model.objects.create_user(
            username="w@example.com", email="w@example.com", password="pw12345678!"
        )
        client.force_login(user)
        from wishlist.models import WishlistItem

        client.post(reverse("storefront:wishlist_toggle", args=[product.id]))
        assert WishlistItem.objects.filter(user=user, product=product).exists()
        client.post(reverse("storefront:wishlist_toggle", args=[product.id]))
        assert not WishlistItem.objects.filter(user=user, product=product).exists()


class TestTranslation:
    def test_key_resolves_per_language(self):
        from storefront.i18n import translate

        assert translate("home.hotOffers", "en") == "Hot Offers"
        assert translate("home.hotOffers", "ar") == "عروض ساخنة"

    def test_missing_key_returns_key(self):
        from storefront.i18n import translate

        assert translate("nope.not.here", "en") == "nope.not.here"

    def test_interpolation(self):
        from storefront.i18n import translate

        assert "3" in translate("product.lowStock", "en", count=3)

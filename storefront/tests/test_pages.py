"""Phase 1 completion smoke tests: product detail, cart page, checkout wizard,
session auth, account section, policy pages. These assert the new views render
and drive the real models — the catalog/cart/orders/accounts suites still own
the business-logic coverage."""
import pytest
from django.urls import reverse

from cart.models import Cart, CartItem
from catalog.tests.factories import BrandFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def product():
    return ProductFactory(brand=BrandFactory(name_en="DR.RASHEL", slug="dr-rashel"),
                          badge_type="bestseller", stock=10, price="8.80")


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="shopper@example.com", email="shopper@example.com",
        password="pw12345678!", first_name="Sam",
    )


@pytest.fixture
def rich_product(db):
    from catalog.models import Category
    return ProductFactory(
        brand=BrandFactory(name_en="ESTELIN", slug="estelin"),
        category=Category.objects.create(name_en="Serum", slug="serum"),
        badge_type="hot_offer", stock=4, price="12.00",
        description_en="A hydrating serum.", benefits_en="Hydrates\nBrightens",
    )


class TestProductDetail:
    def test_renders(self, client, rich_product):
        html = client.get(f"/en/products/{rich_product.slug}/").content.decode()
        assert rich_product.name_en in html
        assert "JOD 12.00" in html
        assert "Hydrates" in html
        assert "/en/shop/" in html

    def test_unknown_slug_404(self, client):
        assert client.get("/en/products/nope-nope/").status_code == 404

    def test_review_requires_login(self, client, rich_product):
        r = client.post(reverse("storefront:review_create", args=[rich_product.id]), {"rating": 5})
        assert r.status_code == 401

    def test_review_create(self, client, user, rich_product):
        client.force_login(user)
        r = client.post(reverse("storefront:review_create", args=[rich_product.id]),
                        {"rating": 4, "body": "Nice"})
        assert r.status_code == 200
        from reviews.models import Review
        assert Review.objects.filter(product=rich_product, user=user, rating=4).exists()
        assert "Nice" in r.content.decode()


class TestCartPage:
    def test_empty_state(self, client):
        assert "cart is empty" in client.get("/en/cart/").content.decode()

    def test_line_and_totals(self, client, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        html = client.get("/en/cart/").content.decode()
        assert product.name_en in html and "cart-summary" in html

    def test_coupon_apply_invalid(self, client, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        r = client.post(reverse("storefront:coupon_apply"), {"code": "NOPE"})
        assert r.status_code == 200 and "cart-summary" in r.content.decode()

    def test_cart_page_qty_update(self, client, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        item = CartItem.objects.get()
        r = client.post(reverse("storefront:cart_update", args=[item.id]),
                        {"page": "cart", "quantity": 2})
        item.refresh_from_db()
        assert item.quantity == 2 and "cart-summary" in r.content.decode()


class TestAuth:
    def test_login_page(self, client):
        assert client.get("/en/login/").status_code == 200

    def test_login_success(self, client, user):
        r = client.post("/en/login/", {"email": "shopper@example.com", "password": "pw12345678!"})
        assert r.status_code == 302 and "_auth_user_id" in client.session

    def test_login_bad_password(self, client, user):
        r = client.post("/en/login/", {"email": "shopper@example.com", "password": "wrong"})
        assert r.status_code == 200 and "_auth_user_id" not in client.session

    def test_register(self, client, django_user_model):
        r = client.post("/en/register/", {"email": "new@example.com", "first_name": "New",
                                          "password": "sturdyPW9182"})
        assert r.status_code == 302
        assert django_user_model.objects.filter(email="new@example.com").exists()

    def test_guest_cart_merges_on_login(self, client, user, product):
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        assert Cart.objects.filter(user=None).exists()
        client.post("/en/login/", {"email": "shopper@example.com", "password": "pw12345678!"})
        merged = Cart.objects.filter(user=user).first()
        assert merged and merged.items.filter(product=product).exists()

    def test_account_requires_login(self, client):
        r = client.get("/en/account/")
        assert r.status_code == 302 and "/login/" in r["Location"]

    def test_forgot_password_sends_reset_email(self, client, user, mailoutbox):
        r = client.post("/en/forgot-password/", {"email": "shopper@example.com"})
        assert r.status_code == 200
        assert "reset link has been sent" in r.content.decode().lower()
        assert len(mailoutbox) == 1
        body = mailoutbox[0].body
        assert "/en/reset-password/?uid=" in body and "token=" in body

    def test_forgot_password_unknown_email_is_silent(self, client, mailoutbox):
        r = client.post("/en/forgot-password/", {"email": "ghost@nowhere.test"})
        assert r.status_code == 200
        assert "reset link has been sent" in r.content.decode().lower()
        assert len(mailoutbox) == 0

    def test_forgot_password_arabic_link(self, client, user, mailoutbox):
        client.post("/ar/forgot-password/", {"email": "shopper@example.com"})
        assert len(mailoutbox) == 1
        assert "/ar/reset-password/?uid=" in mailoutbox[0].body
        assert "كلمة المرور" in mailoutbox[0].subject

    def test_full_password_reset_flow(self, client, user, mailoutbox):
        import re
        client.post("/en/forgot-password/", {"email": "shopper@example.com"})
        m = re.search(r"uid=([^&\s]+)&token=([^&\s]+)", mailoutbox[0].body)
        uid, token = m.group(1), m.group(2)

        assert client.get(f"/en/reset-password/?uid={uid}&token={token}").status_code == 200

        r = client.post("/en/reset-password/",
                        {"uid": uid, "token": token, "password": "brandNewPw99"})
        assert r.status_code == 302
        user.refresh_from_db()
        assert user.check_password("brandNewPw99")
        assert not user.check_password("pw12345678!")

    def test_reset_link_rejected_for_inactive_user(self, client, user):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        html = client.get(f"/en/reset-password/?uid={uid}&token={token}").content.decode()
        assert "invalid or has expired" in html


class TestCheckout:
    def _address(self, user):
        from accounts.models import Address
        return Address.objects.create(user=user, name="Sam", phone="079", city="Amman",
                                      address_line="1 St", is_default=True)

    def test_empty_cart(self, client, user):
        client.force_login(user)
        assert "cart is empty" in client.get("/en/checkout/").content.decode()

    def test_full_checkout_places_order(self, client, user, product):
        from shipping.models import ShippingMethod
        sm = ShippingMethod.objects.create(name_en="Standard", cost="2.00")
        addr = self._address(user)
        client.force_login(user)
        client.post(reverse("storefront:cart_add"), {"product_id": product.id})
        assert client.get("/en/checkout/").status_code == 200
        client.post(reverse("storefront:checkout_step"),
                    {"to": "shipping", "from": "address", "address_id": addr.id})
        client.post(reverse("storefront:checkout_step"),
                    {"to": "payment", "from": "shipping", "shipping_method_id": sm.id})
        client.post(reverse("storefront:checkout_step"),
                    {"to": "review", "from": "payment", "payment_method": "cod"})
        r = client.post(reverse("storefront:checkout_confirm"))
        assert r.status_code == 204 and "/account/orders/" in r["HX-Redirect"]
        from orders.models import Order
        order = Order.objects.filter(user=user).exclude(status="draft").get()
        assert order.status == "pending"
        product.refresh_from_db()
        assert product.stock == 9
        assert not CartItem.objects.filter(cart__user=user).exists()


class TestAccount:
    def test_dashboard(self, client, user):
        client.force_login(user)
        assert "My Account" in client.get("/en/account/").content.decode()

    def test_profile_update(self, client, user):
        client.force_login(user)
        client.post("/en/account/profile/", {"first_name": "Samir", "last_name": "K", "phone": "0791"})
        user.refresh_from_db()
        assert user.first_name == "Samir" and user.phone == "0791"

    def test_address_create_and_delete(self, client, user):
        client.force_login(user)
        client.post(reverse("storefront:account_address_create"),
                    {"name": "Home", "phone": "079", "city": "Amman", "address_line": "2 Rd"})
        from accounts.models import Address
        addr = Address.objects.get(user=user)
        assert addr.is_default
        r = client.post(reverse("storefront:account_address_delete", args=[addr.id]))
        assert r.status_code == 200 and not Address.objects.filter(id=addr.id).exists()

    def test_wishlist_page(self, client, user, product):
        from wishlist.models import WishlistItem
        WishlistItem.objects.create(user=user, product=product)
        client.force_login(user)
        assert product.name_en in client.get("/en/account/wishlist/").content.decode()


class TestSkinQuiz:
    def test_quiz_renders(self, client):
        html = client.get("/en/skin-quiz/").content.decode()
        assert "Find your perfect routine" in html
        assert 'x-data="skinQuiz()"' in html
        assert "skin-quiz-config" in html

    def test_result_fragment_recommends_by_skin_type(self, client, db):
        from catalog.models import ProductAttribute
        st = ProductAttribute.objects.create(
            attribute_type="skin_type", value_en="Oily", slug="oily-skin")
        p = ProductFactory(brand=BrandFactory(slug="dr-rashel"))
        p.attributes.add(st)
        html = client.get("/en/skin-quiz/?result=oily-skin").content.decode()
        assert "oily skin" in html
        assert "/en/skin-type/oily-skin/" in html
        assert p.name_en in html

    def test_result_bad_slug_falls_back(self, client, db):
        r = client.get("/en/skin-quiz/?result=not-a-real-slug")
        assert r.status_code == 200


class TestPolicy:
    def test_renders_body(self, client, db):
        from content.models import Policy
        Policy.objects.update_or_create(slug="privacy-policy",
                                        defaults={"title_en": "Privacy Policy", "body_en": "We respect privacy."})
        html = client.get("/en/policies/privacy-policy/").content.decode()
        assert "We respect privacy." in html

    def test_unknown_slug_404(self, client):
        assert client.get("/en/policies/made-up/").status_code == 404

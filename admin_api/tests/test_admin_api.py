import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import BrandFactory, CategoryFactory, ProductFactory
from orders.models import Order
from promotions.models import Coupon
from reviews.models import Review
from shipping.models import ShippingMethod

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def staff_client():
    staff = User.objects.create_user(username="admin@x.com", email="admin@x.com", password="pw12345678!", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


@pytest.fixture
def customer_client():
    customer = User.objects.create_user(username="cust@x.com", email="cust@x.com", password="pw12345678!")
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


class TestAdminPermissions:
    """Every admin_api endpoint must reject non-staff at the API layer."""

    @pytest.mark.parametrize("url_name", [
        "admin-product-list", "admin-brand-list", "admin-category-list",
        "admin-order-list", "admin-customer-list", "admin-review-list",
        "admin-coupon-list", "admin-shipping-method-list", "admin-payment-list",
    ])
    def test_non_staff_forbidden(self, customer_client, url_name):
        resp = customer_client.get(reverse(url_name))
        assert resp.status_code == 403

    def test_unauthenticated_forbidden(self):
        resp = APIClient().get(reverse("admin-product-list"))
        assert resp.status_code in (401, 403)

    def test_staff_allowed(self, staff_client):
        resp = staff_client.get(reverse("admin-product-list"))
        assert resp.status_code == 200


class TestAdminProductCRUD:
    def test_create_product(self, staff_client):
        brand = BrandFactory()
        resp = staff_client.post(reverse("admin-product-list"), {
            "sku": "NEW-001", "name_en": "New Product", "brand": brand.id, "price": "12.00", "stock": 10,
        })
        assert resp.status_code == 201, resp.data
        assert resp.data["sku"] == "NEW-001"

    def test_update_product(self, staff_client):
        product = ProductFactory(price="10.00")
        resp = staff_client.patch(reverse("admin-product-detail", kwargs={"pk": product.id}), {"price": "15.00"}, format="json")
        assert resp.status_code == 200
        assert resp.data["price"] == "15.00"

    def test_delete_product(self, staff_client):
        product = ProductFactory()
        resp = staff_client.delete(reverse("admin-product-detail", kwargs={"pk": product.id}))
        assert resp.status_code == 204

    def test_search_products(self, staff_client):
        ProductFactory(sku="FINDME-1", name_en="Findable Cream")
        ProductFactory(sku="OTHER-1", name_en="Other Thing")
        resp = staff_client.get(reverse("admin-product-list"), {"search": "Findable"})
        assert resp.data["count"] == 1


class TestAdminCategoryBrandCRUD:
    def test_create_brand(self, staff_client):
        resp = staff_client.post(reverse("admin-brand-list"), {"name_en": "New Brand"})
        assert resp.status_code == 201
        assert resp.data["slug"] == "new-brand"

    def test_create_category(self, staff_client):
        resp = staff_client.post(reverse("admin-category-list"), {"name_en": "New Category"})
        assert resp.status_code == 201

    def test_category_shows_product_count(self, staff_client):
        cat = CategoryFactory()
        ProductFactory(category=cat)
        ProductFactory(category=cat)
        resp = staff_client.get(reverse("admin-category-detail", kwargs={"pk": cat.id}))
        assert resp.data["product_count"] == 2


class TestAdminOrderManagement:
    def test_list_excludes_drafts(self, staff_client):
        customer = User.objects.create_user(username="o@x.com", email="o@x.com", password="pw12345678!")
        Order.objects.create(user=customer, status="draft")
        Order.objects.create(user=customer, status="pending")
        resp = staff_client.get(reverse("admin-order-list"))
        assert resp.data["count"] == 1

    def test_valid_status_transition_via_action(self, staff_client):
        customer = User.objects.create_user(username="o2@x.com", email="o2@x.com", password="pw12345678!")
        order = Order.objects.create(user=customer, status="pending")
        resp = staff_client.post(reverse("admin-order-update-status", kwargs={"pk": order.id}), {"status": "confirmed"})
        assert resp.status_code == 200
        assert resp.data["status"] == "confirmed"

    def test_invalid_status_transition_rejected(self, staff_client):
        customer = User.objects.create_user(username="o3@x.com", email="o3@x.com", password="pw12345678!")
        order = Order.objects.create(user=customer, status="pending")
        resp = staff_client.post(reverse("admin-order-update-status", kwargs={"pk": order.id}), {"status": "shipped"})
        assert resp.status_code == 400
        order.refresh_from_db()
        assert order.status == "pending"  # unchanged


class TestAdminCustomers:
    def test_lists_customers_not_staff(self, staff_client):
        User.objects.create_user(username="c1@x.com", email="c1@x.com", password="pw12345678!")
        User.objects.create_user(username="staffonly@x.com", email="staffonly@x.com", password="pw12345678!", is_staff=True)
        resp = staff_client.get(reverse("admin-customer-list"))
        emails = [c["email"] for c in resp.data["results"]]
        assert "c1@x.com" in emails
        assert "staffonly@x.com" not in emails

    def test_toggle_active(self, staff_client):
        customer = User.objects.create_user(username="c2@x.com", email="c2@x.com", password="pw12345678!")
        resp = staff_client.post(reverse("admin-customer-toggle-active", kwargs={"pk": customer.id}))
        assert resp.status_code == 200
        assert resp.data["is_active"] is False


class TestAdminReviewModeration:
    def test_approve_review(self, staff_client):
        customer = User.objects.create_user(username="r@x.com", email="r@x.com", password="pw12345678!")
        product = ProductFactory()
        review = Review.objects.create(user=customer, product=product, rating=1, is_approved=True)
        resp = staff_client.patch(reverse("admin-review-detail", kwargs={"pk": review.id}), {"is_approved": False}, format="json")
        assert resp.status_code == 200
        assert resp.data["is_approved"] is False

    def test_cannot_rewrite_review_content(self, staff_client):
        customer = User.objects.create_user(username="r2@x.com", email="r2@x.com", password="pw12345678!")
        product = ProductFactory()
        review = Review.objects.create(user=customer, product=product, rating=5, body="original")
        staff_client.patch(reverse("admin-review-detail", kwargs={"pk": review.id}), {"body": "tampered"}, format="json")
        review.refresh_from_db()
        assert review.body == "original"  # body is read-only in the admin serializer


class TestAdminCoupons:
    def test_create_and_deactivate_coupon(self, staff_client):
        create_resp = staff_client.post(reverse("admin-coupon-list"), {
            "code": "ADMINTEST", "discount_type": "percent", "discount_value": "15.00",
        })
        assert create_resp.status_code == 201
        coupon_id = create_resp.data["id"]

        deactivate_resp = staff_client.patch(reverse("admin-coupon-detail", kwargs={"pk": coupon_id}), {"is_active": False}, format="json")
        assert deactivate_resp.status_code == 200
        assert Coupon.objects.get(id=coupon_id).is_active is False


class TestAdminShipping:
    def test_create_shipping_method(self, staff_client):
        resp = staff_client.post(reverse("admin-shipping-method-list"), {"name_en": "Overnight", "cost": "8.00"})
        assert resp.status_code == 201
        assert ShippingMethod.objects.filter(name_en="Overnight").exists()

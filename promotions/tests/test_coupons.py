import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory
from promotions.models import Coupon

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


class TestCouponModel:
    def test_percent_discount_calculation(self):
        coupon = Coupon.objects.create(code="SAVE10", discount_type="percent", discount_value=10)
        assert coupon.calculate_discount(100) == 10.0

    def test_fixed_discount_capped_at_subtotal(self):
        coupon = Coupon.objects.create(code="FLAT50", discount_type="fixed", discount_value=50)
        assert coupon.calculate_discount(20) == 20  # can't discount more than the order is worth

    def test_expired_coupon_invalid(self):
        coupon = Coupon.objects.create(
            code="OLD", discount_type="percent", discount_value=10,
            valid_until=timezone.now() - timedelta(days=1),
        )
        valid, _ = coupon.is_valid_now()
        assert valid is False

    def test_usage_limit_reached_invalid(self):
        coupon = Coupon.objects.create(code="LIMITED", discount_type="percent", discount_value=10, max_uses=1, times_used=1)
        valid, _ = coupon.is_valid_now()
        assert valid is False


class TestApplyCouponEndpoint:
    def test_apply_valid_coupon_to_cart(self, client):
        Coupon.objects.create(code="SAVE10", discount_type="percent", discount_value=10)
        product = ProductFactory(price="100.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})

        resp = client.post(reverse("cart-apply-coupon"), {"code": "save10"})  # case-insensitive
        assert resp.status_code == 200
        assert resp.data["coupon_code"] == "SAVE10"
        assert resp.data["discount_amount"] == "10.00"
        assert resp.data["total"] == "90.00"

    def test_apply_unknown_coupon(self, client):
        resp = client.post(reverse("cart-apply-coupon"), {"code": "NOPE"})
        assert resp.status_code == 404

    def test_apply_below_minimum_order_value(self, client):
        Coupon.objects.create(code="BIG20", discount_type="fixed", discount_value=20, min_order_value=100)
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})

        resp = client.post(reverse("cart-apply-coupon"), {"code": "BIG20"})
        assert resp.status_code == 400

    def test_remove_coupon(self, client):
        Coupon.objects.create(code="SAVE10", discount_type="percent", discount_value=10)
        client.post(reverse("cart-apply-coupon"), {"code": "SAVE10"})
        resp = client.delete(reverse("cart-apply-coupon"))
        assert resp.data["coupon_code"] == ""

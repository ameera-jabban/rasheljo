import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Address
from catalog.tests.factories import ProductFactory
from promotions.models import Coupon
from shipping.models import ShippingMethod

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def auth_client():
    user = User.objects.create_user(username="s@s.com", email="s@s.com", password="pw12345678!")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


class TestShippingMethodList:
    def test_lists_active_methods_only(self):
        ShippingMethod.objects.create(name_en="Standard", cost="2.00", is_active=True)
        ShippingMethod.objects.create(name_en="Retired", cost="1.00", is_active=False)
        resp = APIClient().get(reverse("shipping-method-list"))
        assert len(resp.data) == 1
        assert resp.data[0]["name_en"] == "Standard"


class TestFullCheckoutWithShippingAndCoupon:
    def test_order_total_includes_shipping_and_discount(self, auth_client):
        client, user = auth_client
        address = Address.objects.create(user=user, name="T", phone="0776661237", city="Amman", address_line="St 1")
        method = ShippingMethod.objects.create(name_en="Standard", cost="3.00")
        Coupon.objects.create(code="SAVE10", discount_type="percent", discount_value=10)

        product = ProductFactory(price="100.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        client.post(reverse("cart-apply-coupon"), {"code": "SAVE10"})

        create_resp = client.post(reverse("order-create"), {
            "address_id": address.id, "shipping_method_id": method.id,
        })
        assert create_resp.status_code == 201
        # subtotal 100, shipping 3, discount 10 -> total 93
        assert create_resp.data["subtotal"] == "100.00"
        assert create_resp.data["shipping_cost"] == "3.00"
        assert create_resp.data["discount_amount"] == "10.00"
        assert create_resp.data["total"] == "93.00"

        confirm_resp = client.post(reverse("order-confirm", kwargs={"pk": create_resp.data["id"]}))
        assert confirm_resp.status_code == 200
        assert confirm_resp.data["status"] == "pending"

        coupon = Coupon.objects.get(code="SAVE10")
        assert coupon.times_used == 1

    def test_update_draft_order_shipping_method_via_patch(self, auth_client):
        client, user = auth_client
        address = Address.objects.create(user=user, name="T", phone="0776661237", city="Amman", address_line="St 1")
        method = ShippingMethod.objects.create(name_en="Express", cost="5.00")
        product = ProductFactory(price="20.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})

        create_resp = client.post(reverse("order-create"))
        order_id = create_resp.data["id"]

        patch_resp = client.patch(
            reverse("order-update-draft", kwargs={"pk": order_id}),
            {"address_id": address.id, "shipping_method_id": method.id, "payment_method": "cod"},
            format="json",
        )
        assert patch_resp.status_code == 200
        assert patch_resp.data["shipping_method"]["id"] == method.id
        assert patch_resp.data["total"] == "25.00"

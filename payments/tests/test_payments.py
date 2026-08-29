import pytest
from django.contrib.auth import get_user_model

from accounts.models import Address
from catalog.tests.factories import ProductFactory
from orders.models import Order, OrderItem
from payments.models import Payment
from payments.services import process_payment

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestPaymentServices:
    def test_cod_payment_succeeds_immediately(self):
        user = User.objects.create_user(username="pay@x.com", email="pay@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="cod", total="20.00")
        payment = process_payment(order)
        assert payment.status == "paid"
        assert payment.attempts.first().success is True

    def test_card_payment_fails_without_gateway_configured(self):
        user = User.objects.create_user(username="pay2@x.com", email="pay2@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="card", total="20.00")
        payment = process_payment(order)
        assert payment.status == "failed"
        assert payment.attempts.first().success is False

    def test_card_order_confirm_rolls_back_on_payment_failure(self):
        from django.urls import reverse
        from rest_framework.test import APIClient

        user = User.objects.create_user(username="pay3@x.com", email="pay3@x.com", password="pw12345678!")
        address = Address.objects.create(user=user, name="T", phone="0776661237", city="Amman", address_line="St 1")
        product = ProductFactory(price="10.00", stock=5)

        client = APIClient()
        client.force_authenticate(user=user)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        create_resp = client.post(reverse("order-create"), {"address_id": address.id, "payment_method": "card"})

        resp = client.post(reverse("order-confirm", kwargs={"pk": create_resp.data["id"]}))
        assert resp.status_code == 402

        product.refresh_from_db()
        assert product.stock == 5  # stock decrement was rolled back

        order = Order.objects.get(id=create_resp.data["id"])
        assert order.status == "draft"  # never actually confirmed

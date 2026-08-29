import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Address
from catalog.tests.factories import ProductFactory
from orders.models import Order

pytestmark = pytest.mark.django_db
User = get_user_model()


def make_address(user):
    return Address.objects.create(
        user=user, name="Test User", phone="0776661237", city="Amman", address_line="Rainbow St 12",
    )


@pytest.fixture
def auth_client():
    user = User.objects.create_user(username="a@b.com", email="a@b.com", password="pw12345678!")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


class TestOrderStateMachine:
    def test_cannot_skip_straight_to_shipped(self):
        user = User.objects.create_user(username="x@y.com", email="x@y.com", password="pw12345678!")
        order = Order.objects.create(user=user)  # starts as draft
        with pytest.raises(ValueError):
            order.transition_to("shipped")

    def test_valid_transition_chain_and_history_logged(self):
        user = User.objects.create_user(username="z@z.com", email="z@z.com", password="pw12345678!")
        order = Order.objects.create(user=user)
        for step in ["pending", "confirmed", "processing", "shipped", "delivered"]:
            order.transition_to(step)
        assert order.status == "delivered"
        assert order.status_history.count() == 5

    def test_delivered_is_terminal(self):
        user = User.objects.create_user(username="w@w.com", email="w@w.com", password="pw12345678!")
        order = Order.objects.create(user=user, status="delivered")
        with pytest.raises(ValueError):
            order.transition_to("cancelled")


class TestCheckoutEndpoints:
    def test_create_order_from_cart_snapshots_items(self, auth_client):
        client, user = auth_client
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 2})

        resp = client.post(reverse("order-create"))
        assert resp.status_code == 201
        assert resp.data["status"] == "draft"
        assert resp.data["subtotal"] == "20.00"
        assert len(resp.data["items"]) == 1

    def test_cannot_create_order_from_empty_cart(self, auth_client):
        client, user = auth_client
        resp = client.post(reverse("order-create"))
        assert resp.status_code == 400

    def test_confirm_requires_shipping_address(self, auth_client):
        client, user = auth_client
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        create_resp = client.post(reverse("order-create"))
        resp = client.post(reverse("order-confirm", kwargs={"pk": create_resp.data["id"]}))
        assert resp.status_code == 400

    def test_confirm_decrements_stock_and_clears_cart(self, auth_client):
        client, user = auth_client
        address = make_address(user)
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 2})
        create_resp = client.post(reverse("order-create"), {"address_id": address.id})
        order_id = create_resp.data["id"]

        confirm_resp = client.post(reverse("order-confirm", kwargs={"pk": order_id}))
        assert confirm_resp.status_code == 200
        assert confirm_resp.data["status"] == "pending"

        product.refresh_from_db()
        assert product.stock == 3  # 5 - 2

        cart_resp = client.get(reverse("cart-detail"))
        assert cart_resp.data["items"] == []

    def test_confirm_rejects_oversold_stock_between_draft_and_confirm(self, auth_client):
        """The anti-oversell check from the spec: stock drops below what was
        drafted (e.g. another customer bought it) before this order is confirmed."""
        client, user = auth_client
        address = make_address(user)
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 3})
        create_resp = client.post(reverse("order-create"), {"address_id": address.id})
        order_id = create_resp.data["id"]

        # Simulate stock being consumed elsewhere between draft and confirm.
        product.stock = 1
        product.save(update_fields=["stock"])

        confirm_resp = client.post(reverse("order-confirm", kwargs={"pk": order_id}))
        assert confirm_resp.status_code == 409

    def test_order_list_excludes_drafts(self, auth_client):
        client, user = auth_client
        Order.objects.create(user=user, status="draft")
        Order.objects.create(user=user, status="pending")

        resp = client.get(reverse("order-list"))
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["status"] == "pending"

    def test_cannot_view_other_users_orders(self, auth_client):
        client, user = auth_client
        other_user = User.objects.create_user(username="other@x.com", email="other@x.com", password="pw12345678!")
        other_order = Order.objects.create(user=other_user, status="pending")

        resp = client.get(reverse("order-detail", kwargs={"pk": other_order.id}))
        assert resp.status_code == 404


class TestCheckoutSurvivesBrokerOutage:
    """Regression: a Celery broker outage must never break order confirmation.

    The order-status-change signal and the confirmation email are best-effort
    side effects. Real dev/prod run with CELERY_TASK_ALWAYS_EAGER=False, so
    `.delay()` opens a broker connection — when that fails (broker down, or an
    incompatibly-old Redis) it raised `kombu.exceptions.OperationalError` out of
    the confirm view, 500-ing checkout and leaving the order stuck at 'draft'.
    The test suite's eager mode hid this, so these tests force the failure.
    """

    @staticmethod
    def _break_broker(monkeypatch):
        from kombu.exceptions import OperationalError

        from notify import tasks

        def boom(*args, **kwargs):
            raise OperationalError("unknown command 'HELLO'")

        monkeypatch.setattr(tasks.send_order_status_update, "delay", boom)
        monkeypatch.setattr(tasks.send_order_confirmation_email, "delay", boom)
        monkeypatch.setattr(tasks.send_review_request_email, "delay", boom)

    def test_cod_confirm_succeeds_when_broker_is_down(self, auth_client, monkeypatch):
        self._break_broker(monkeypatch)
        client, user = auth_client
        address = make_address(user)
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 2})
        create_resp = client.post(reverse("order-create"), {"address_id": address.id})
        order_id = create_resp.data["id"]

        confirm_resp = client.post(reverse("order-confirm", kwargs={"pk": order_id}))

        assert confirm_resp.status_code == 200
        assert confirm_resp.data["status"] == "pending"

        product.refresh_from_db()
        assert product.stock == 3  # stock still decremented
        assert client.get(reverse("cart-detail")).data["items"] == []  # cart still cleared
        assert Order.objects.get(id=order_id).status == "pending"  # not rolled back to draft

    def test_card_still_fails_cleanly_when_broker_is_down(self, auth_client, monkeypatch):
        """The broker-outage handling must not accidentally turn a failed card
        payment into a success."""
        self._break_broker(monkeypatch)
        client, user = auth_client
        address = make_address(user)
        product = ProductFactory(price="10.00", stock=5)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        create_resp = client.post(
            reverse("order-create"), {"address_id": address.id, "payment_method": "card"}
        )
        order_id = create_resp.data["id"]

        confirm_resp = client.post(reverse("order-confirm", kwargs={"pk": order_id}))

        assert confirm_resp.status_code == 402
        assert "detail" in confirm_resp.data
        product.refresh_from_db()
        assert product.stock == 5  # rolled back
        assert Order.objects.get(id=order_id).status == "draft"

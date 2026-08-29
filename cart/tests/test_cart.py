import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


class TestGuestCart:
    def test_add_item_creates_cart_and_item(self, client):
        product = ProductFactory(price="10.00", stock=5)
        resp = client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 2})
        assert resp.status_code == 201
        assert len(resp.data["items"]) == 1
        assert resp.data["items"][0]["quantity"] == 2
        assert resp.data["subtotal"] == "20.00"

    def test_adding_same_product_twice_increments_quantity_not_duplicates_row(self, client):
        product = ProductFactory(price="10.00", stock=10)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        resp = client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 2})
        assert len(resp.data["items"]) == 1
        assert resp.data["items"][0]["quantity"] == 3

    def test_cannot_add_more_than_stock(self, client):
        product = ProductFactory(stock=2)
        resp = client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 5})
        assert resp.status_code == 400

    def test_cart_persists_across_requests_via_session(self, client):
        product = ProductFactory(stock=10)
        client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        resp = client.get(reverse("cart-detail"))
        assert len(resp.data["items"]) == 1

    def test_update_item_quantity(self, client):
        product = ProductFactory(stock=10)
        add_resp = client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        item_id = add_resp.data["items"][0]["id"]

        resp = client.patch(
            reverse("cart-item-detail", kwargs={"pk": item_id}), {"quantity": 4}, format="json"
        )
        assert resp.data["items"][0]["quantity"] == 4

    def test_remove_item(self, client):
        product = ProductFactory(stock=10)
        add_resp = client.post(reverse("cart-item-create"), {"product_id": product.id, "quantity": 1})
        item_id = add_resp.data["items"][0]["id"]

        resp = client.delete(reverse("cart-item-detail", kwargs={"pk": item_id}))
        assert resp.data["items"] == []

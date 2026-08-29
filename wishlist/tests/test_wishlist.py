import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def auth_client():
    user = User.objects.create_user(username="w@w.com", email="w@w.com", password="pw12345678!")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestWishlist:
    def test_requires_auth(self):
        client = APIClient()
        resp = client.get(reverse("wishlist-list"))
        assert resp.status_code == 401

    def test_add_and_list(self, auth_client):
        product = ProductFactory()
        resp = auth_client.post(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        assert resp.status_code == 201

        list_resp = auth_client.get(reverse("wishlist-list"))
        assert len(list_resp.data) == 1
        assert list_resp.data[0]["product"]["id"] == product.id

    def test_adding_twice_is_idempotent(self, auth_client):
        product = ProductFactory()
        auth_client.post(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        resp = auth_client.post(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        assert resp.status_code == 200  # not 201 the second time
        assert len(auth_client.get(reverse("wishlist-list")).data) == 1

    def test_remove(self, auth_client):
        product = ProductFactory()
        auth_client.post(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        resp = auth_client.delete(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        assert resp.status_code == 204
        assert len(auth_client.get(reverse("wishlist-list")).data) == 0

    def test_remove_not_wishlisted_returns_404(self, auth_client):
        product = ProductFactory()
        resp = auth_client.delete(reverse("wishlist-toggle", kwargs={"product_id": product.id}))
        assert resp.status_code == 404

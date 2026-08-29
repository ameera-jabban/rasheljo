import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory
from orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def auth_client():
    user = User.objects.create_user(username="r@r.com", email="r@r.com", password="pw12345678!")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


class TestReviews:
    def test_anyone_can_list_reviews(self):
        product = ProductFactory()
        resp = APIClient().get(reverse("review-list"), {"product": product.id})
        assert resp.status_code == 200

    def test_unauthenticated_cannot_post(self):
        product = ProductFactory()
        resp = APIClient().post(reverse("review-list"), {"product": product.id, "rating": 5})
        assert resp.status_code == 401

    def test_authenticated_can_post_review(self, auth_client):
        client, user = auth_client
        product = ProductFactory()
        resp = client.post(reverse("review-list"), {"product": product.id, "rating": 4, "body": "Nice cream"})
        assert resp.status_code == 201
        assert resp.data["is_verified_purchase"] is False

    def test_cannot_review_same_product_twice(self, auth_client):
        client, user = auth_client
        product = ProductFactory()
        client.post(reverse("review-list"), {"product": product.id, "rating": 4})
        resp = client.post(reverse("review-list"), {"product": product.id, "rating": 2})
        assert resp.status_code == 400

    def test_review_links_to_delivered_order_as_verified_purchase(self, auth_client):
        client, user = auth_client
        product = ProductFactory()
        order = Order.objects.create(user=user, status="delivered")
        OrderItem.objects.create(order=order, product=product, product_name=product.name_en, unit_price="10.00", quantity=1)

        resp = client.post(reverse("review-list"), {"product": product.id, "rating": 5})
        assert resp.data["is_verified_purchase"] is True

    def test_rating_out_of_range_rejected(self, auth_client):
        client, user = auth_client
        product = ProductFactory()
        resp = client.post(reverse("review-list"), {"product": product.id, "rating": 6})
        assert resp.status_code == 400

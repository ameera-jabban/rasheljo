import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory
from orders.models import Order

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestAdminDashboard:
    def test_requires_staff(self):
        user = User.objects.create_user(username="notstaff@x.com", email="notstaff@x.com", password="pw12345678!")
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get(reverse("admin-dashboard-stats"))
        assert resp.status_code == 403

    def test_staff_sees_real_counts(self):
        staff = User.objects.create_user(
            username="staff@x.com", email="staff@x.com", password="pw12345678!", is_staff=True
        )
        customer = User.objects.create_user(username="cust@x.com", email="cust@x.com", password="pw12345678!")
        ProductFactory(stock=3)  # low stock
        ProductFactory(stock=0)  # out of stock
        Order.objects.create(user=customer, status="pending", total="50.00")
        Order.objects.create(user=customer, status="draft", total="10.00")  # excluded

        client = APIClient()
        client.force_authenticate(user=staff)
        resp = client.get(reverse("admin-dashboard-stats"))
        assert resp.status_code == 200
        assert resp.data["orders_total"] == 1  # draft excluded
        assert resp.data["low_stock_products"] >= 1
        assert resp.data["out_of_stock_products"] >= 1
        assert resp.data["customers_total"] >= 1

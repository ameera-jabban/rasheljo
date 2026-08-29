from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.tests.factories import BrandFactory, CategoryFactory, ProductFactory
from orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db
User = get_user_model()

REPORT_URLS = [
    "admin-reports-sales-over-time",
    "admin-reports-top-products",
    "admin-reports-revenue-by-brand",
    "admin-reports-revenue-by-category",
    "admin-reports-inventory",
    "admin-reports-order-summary",
]


@pytest.fixture
def staff_client():
    staff = User.objects.create_user(
        username="rep-staff@x.com", email="rep-staff@x.com", password="pw12345678!", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


@pytest.fixture
def customer():
    return User.objects.create_user(username="rep-cust@x.com", email="rep-cust@x.com", password="pw12345678!")


def _order(customer, *, status, total, days_ago=1, items=None):
    o = Order.objects.create(user=customer, status=status, total=total)
    # created_at is auto_now_add — override it explicitly for time-range tests.
    Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    o.refresh_from_db()
    for product, qty, unit_price in items or []:
        OrderItem.objects.create(
            order=o, product=product, product_name=product.name_en, unit_price=unit_price, quantity=qty
        )
    return o


class TestReportsPermissions:
    @pytest.mark.parametrize("url_name", REPORT_URLS)
    def test_non_staff_forbidden(self, customer, url_name):
        client = APIClient()
        client.force_authenticate(user=customer)
        assert client.get(reverse(url_name)).status_code == 403

    @pytest.mark.parametrize("url_name", REPORT_URLS)
    def test_staff_ok(self, staff_client, url_name):
        assert staff_client.get(reverse(url_name)).status_code == 200


class TestSalesOverTime:
    def test_revenue_and_order_counts_bucketed(self, staff_client, customer):
        _order(customer, status="confirmed", total="50.00", days_ago=2)
        _order(customer, status="delivered", total="30.00", days_ago=2)  # same day bucket
        _order(customer, status="pending", total="99.00", days_ago=2)  # not paid -> excluded
        _order(customer, status="confirmed", total="20.00", days_ago=40)  # outside 30d

        resp = staff_client.get(reverse("admin-reports-sales-over-time"), {"range": "30d"})
        assert resp.status_code == 200
        series = resp.data["series"]
        assert sum(p["revenue"] for p in series) == pytest.approx(80.0)  # 50 + 30
        assert sum(p["orders"] for p in series) == 2
        # continuous daily axis for 30d
        assert resp.data["bucket"] == "day"
        assert len(series) >= 30

    def test_longer_range_uses_coarser_buckets(self, staff_client):
        assert staff_client.get(reverse("admin-reports-sales-over-time"), {"range": "1y"}).data["bucket"] == "month"
        assert staff_client.get(reverse("admin-reports-sales-over-time"), {"range": "90d"}).data["bucket"] == "week"


class TestTopProducts:
    def test_ranks_by_units_and_revenue(self, staff_client, customer):
        cheap = ProductFactory(name_en="Cheap Popular", price="5.00")
        pricey = ProductFactory(name_en="Pricey Niche", price="80.00")
        _order(customer, status="confirmed", total="0", days_ago=1, items=[(cheap, 10, "5.00")])   # 10 units, 50 rev
        _order(customer, status="delivered", total="0", days_ago=3, items=[(pricey, 2, "80.00")])  # 2 units, 160 rev

        resp = staff_client.get(reverse("admin-reports-top-products"), {"range": "30d"})
        assert resp.data["by_units"][0]["name"] == "Cheap Popular"
        assert resp.data["by_units"][0]["units"] == 10
        assert resp.data["by_revenue"][0]["name"] == "Pricey Niche"
        assert resp.data["by_revenue"][0]["revenue"] == pytest.approx(160.0)

    def test_excludes_unpaid_orders(self, staff_client, customer):
        p = ProductFactory()
        _order(customer, status="pending", total="0", items=[(p, 5, "10.00")])
        resp = staff_client.get(reverse("admin-reports-top-products"))
        assert resp.data["by_units"] == []


class TestRevenueByBrandCategory:
    def test_groups_revenue_by_brand(self, staff_client, customer):
        b1 = BrandFactory(name_en="Alpha")
        b2 = BrandFactory(name_en="Beta")
        pa = ProductFactory(brand=b1)
        pb = ProductFactory(brand=b2)
        _order(customer, status="confirmed", total="0", items=[(pa, 3, "10.00")])  # Alpha 30
        _order(customer, status="confirmed", total="0", items=[(pb, 1, "25.00")])  # Beta 25

        resp = staff_client.get(reverse("admin-reports-revenue-by-brand"))
        by_name = {r["name"]: r["revenue"] for r in resp.data["brands"]}
        assert by_name["Alpha"] == pytest.approx(30.0)
        assert by_name["Beta"] == pytest.approx(25.0)

    def test_groups_revenue_by_category(self, staff_client, customer):
        c1 = CategoryFactory(name_en="Serums")
        p = ProductFactory(category=c1)
        _order(customer, status="delivered", total="0", items=[(p, 4, "12.50")])  # 50
        resp = staff_client.get(reverse("admin-reports-revenue-by-category"))
        assert resp.data["categories"][0]["name"] == "Serums"
        assert resp.data["categories"][0]["revenue"] == pytest.approx(50.0)


class TestInventoryReport:
    def test_value_and_low_out_lists(self, staff_client):
        ProductFactory(sku="OK-1", name_en="Healthy", price="10.00", stock=100)   # value 1000
        ProductFactory(sku="LOW-1", name_en="Running Low", price="20.00", stock=3)  # value 60, low
        ProductFactory(sku="OUT-1", name_en="Sold Out", price="15.00", stock=0)     # value 0, out

        resp = staff_client.get(reverse("admin-reports-inventory"))
        assert resp.data["total_inventory_value"] == pytest.approx(1060.0)
        assert resp.data["low_stock_count"] == 1
        assert resp.data["out_of_stock_count"] == 1
        assert resp.data["low_stock_products"][0]["sku"] == "LOW-1"
        assert resp.data["low_stock_products"][0]["stock"] == 3
        assert resp.data["out_of_stock_products"][0]["sku"] == "OUT-1"


class TestOrderSummary:
    def test_aov_and_status_breakdown(self, staff_client, customer):
        _order(customer, status="confirmed", total="100.00", days_ago=1)
        _order(customer, status="delivered", total="50.00", days_ago=2)
        _order(customer, status="cancelled", total="999.00", days_ago=2)  # counted in status breakdown, not revenue
        _order(customer, status="draft", total="10.00", days_ago=1)  # excluded entirely

        resp = staff_client.get(reverse("admin-reports-order-summary"), {"range": "30d"})
        assert resp.data["total_orders"] == 3  # confirmed + delivered + cancelled (draft excluded)
        assert resp.data["paid_orders"] == 2
        assert resp.data["total_revenue"] == pytest.approx(150.0)
        assert resp.data["average_order_value"] == pytest.approx(75.0)  # 150 / 2
        assert resp.data["orders_by_status"]["cancelled"] == 1
        assert "draft" not in resp.data["orders_by_status"]

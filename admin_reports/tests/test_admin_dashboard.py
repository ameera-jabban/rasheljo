"""The Django Admin (/admin/) index stats dashboard + the Product 'stock level'
filter its links point at."""
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from catalog.tests.factories import ProductFactory
from orders.models import Order

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(
        username="boss@x.com", email="boss@x.com", password="pw12345678!"
    )


class TestAdminIndexDashboard:
    def test_index_renders_stats_section_with_actionable_links(self, client, admin_user):
        ProductFactory(stock=3)
        ProductFactory(stock=0)
        client.force_login(admin_user)
        html = client.get(reverse("admin:index")).content.decode()

        assert "Store analytics" in html
        assert "Stock alerts" in html
        assert "Orders by status" in html
        assert "Top sellers" in html
        # low/out-of-stock counts link into the filtered Product changelist
        assert "/catalog/product/?stock_level=low" in html
        assert "/catalog/product/?stock_level=out" in html
        # normal app list is still rendered below the stats
        assert "/catalog/product/" in html

    def test_dashboard_numbers_match_database(self, admin_user):
        from admin_reports.dashboard import dashboard_callback

        ProductFactory(stock=2)
        ProductFactory(stock=9)   # 2 low
        ProductFactory(stock=0)   # 1 out
        ProductFactory(stock=40)  # in stock
        cust = User.objects.create_user(username="c@x.com", email="c@x.com", password="pw12345678!")
        Order.objects.create(user=cust, status="delivered", total="120.00")
        Order.objects.create(user=cust, status="pending", total="30.00")

        ctx = dashboard_callback(RequestFactory().get("/admin/"), {})
        d = ctx["stats_dashboard"]

        low = next(s for s in d["stock_alerts"] if s["label"] == "Low stock")
        out = next(s for s in d["stock_alerts"] if s["label"] == "Out of stock")
        assert low["value"] == 2
        assert out["value"] == 1
        assert dict((o["status"], o["count"]) for o in d["orders_by_status"]) == {
            "delivered": 1, "pending": 1
        }
        # last-30-day revenue counts only the paid (delivered) order
        assert d["revenue"][-1]["value"] == pytest.approx(120.0)

    def test_normal_admin_pages_unaffected(self, client, admin_user):
        ProductFactory(stock=5)
        client.force_login(admin_user)
        assert client.get("/admin/catalog/product/").status_code == 200
        assert client.get("/admin/orders/order/").status_code == 200


class TestStockLevelFilter:
    def test_filter_options(self, client, admin_user):
        client.force_login(admin_user)
        p_out = ProductFactory(stock=0)
        p_low = ProductFactory(stock=4)
        p_in = ProductFactory(stock=25)

        def ids(qs_url):
            r = client.get(qs_url)
            assert r.status_code == 200
            return {o.pk for o in r.context["cl"].result_list}

        assert ids("/admin/catalog/product/?stock_level=out") == {p_out.pk}
        assert ids("/admin/catalog/product/?stock_level=low") == {p_low.pk}
        assert ids("/admin/catalog/product/?stock_level=in") == {p_in.pk}
        assert ids("/admin/catalog/product/") == {p_out.pk, p_low.pk, p_in.pk}

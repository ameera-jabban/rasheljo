"""Django Admin index dashboard.

Wired via ``UNFOLD["DASHBOARD_CALLBACK"]``. Surfaces the SAME aggregation the
REST reports endpoints use (``admin_reports.views.dashboard_stats`` +
``admin_reports.reports.inventory_data`` / ``top_products_data``) inside the
built-in ``/admin/`` index page — no metric is recomputed a second way here.
"""
from datetime import timedelta

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from orders.models import Order

from .reports import PAID_STATUSES, _money, inventory_data, top_products_data
from .views import dashboard_stats


def _paid_revenue_since(start):
    return Order.objects.filter(
        status__in=PAID_STATUSES, created_at__gte=start
    ).aggregate(t=Sum("total"))["t"] or 0


def dashboard_callback(request, context):
    """Populate ``context`` for templates/admin/index.html. Failures here must
    not take down the admin index, so the template guards on ``stats_dashboard``
    and this stays defensive."""
    try:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())

        stats = dashboard_stats()
        inv = inventory_data()
        top = top_products_data(now - timedelta(days=30), limit=5)["by_units"]

        product_url = reverse("admin:catalog_product_changelist")
        order_url = reverse("admin:orders_order_changelist")

        context["stats_dashboard"] = {
            "revenue": [
                {"label": "Today", "value": _money(_paid_revenue_since(today_start))},
                {"label": "This week", "value": _money(_paid_revenue_since(week_start))},
                {"label": "Last 30 days", "value": _money(float(stats["revenue_last_30_days"]))},
            ],
            "counts": [
                {"label": "Customers", "value": stats["customers_total"]},
                {"label": "Active products", "value": stats["products_total"]},
                {"label": "Orders (all time)", "value": stats["orders_total"], "url": order_url},
                {"label": "Inventory value", "value": inv["total_inventory_value"], "money": True},
            ],
            "orders_by_status": [
                {"status": s, "count": c, "url": f"{order_url}?status__exact={s}"}
                for s, c in sorted(stats["orders_by_status"].items())
            ],
            "stock_alerts": [
                {
                    "label": "Low stock",
                    "value": inv["low_stock_count"],
                    "url": f"{product_url}?stock_level=low",
                    "tone": "warn",
                },
                {
                    "label": "Out of stock",
                    "value": inv["out_of_stock_count"],
                    "url": f"{product_url}?stock_level=out",
                    "tone": "danger",
                },
            ],
            "top_products": [
                {
                    "name": p["name"],
                    "units": p["units"],
                    "revenue": p["revenue"],
                    "url": (f"{product_url}{p['product_id']}/change/" if p["product_id"] else product_url),
                }
                for p in top
            ],
        }
    except Exception:  # pragma: no cover - never break /admin/ over a dashboard error
        import logging

        logging.getLogger("admin_reports.dashboard").exception("Admin dashboard callback failed")
    return context

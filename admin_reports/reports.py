"""Deeper analytics endpoints for the admin Reports page — sales trend, top
products, revenue breakdowns, inventory and order summary. All aggregation is
done in the database (annotate/aggregate + Trunc bucketing), never by looping
orders in Python.
"""
from datetime import timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.permissions import IsStaffUser
from catalog.models import Product
from orders.models import Order, OrderItem

# Statuses that represent real, counted revenue (matches AdminDashboardStatsView).
PAID_STATUSES = ["confirmed", "processing", "shipped", "delivered"]
LOW_STOCK_THRESHOLD = 10

# range key -> (days back, bucket granularity)
RANGES = {
    "7d": (7, "day"),
    "30d": (30, "day"),
    "90d": (90, "week"),
    "1y": (365, "month"),
}
_TRUNC = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}

_line_total = ExpressionWrapper(
    F("unit_price") * F("quantity"),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)


def _resolve_range(request):
    key = request.query_params.get("range", "30d")
    if key not in RANGES:
        key = "30d"
    days, bucket = RANGES[key]
    start = timezone.now() - timedelta(days=days)
    return key, start, bucket


def _money(value):
    return round(float(value or 0), 2)


class _StaffView(APIView):
    permission_classes = [IsStaffUser]


def _floor_date(d, bucket):
    """Snap a date to the start of its day / ISO week (Monday) / month."""
    if bucket == "month":
        return d.replace(day=1)
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    return d


def _next_bucket(d, bucket):
    if bucket == "month":
        return (d.replace(day=28) + timedelta(days=7)).replace(day=1)
    return d + timedelta(weeks=1 if bucket == "week" else 0, days=0 if bucket == "week" else 1)


class SalesOverTimeView(_StaffView):
    """GET /api/v1/admin/reports/sales-over-time/?range=7d|30d|90d|1y
    Revenue + order-count time series for paid orders, bucketed (daily for short
    ranges, weekly at 90d, monthly at 1y), with empty buckets zero-filled."""

    def get(self, request):
        key, start, bucket = _resolve_range(request)
        trunc = _TRUNC[bucket]

        rows = (
            Order.objects.filter(status__in=PAID_STATUSES, created_at__gte=start)
            .annotate(bucket=trunc("created_at"))
            .values("bucket")
            .annotate(revenue=Sum("total"), orders=Count("id"))
            .order_by("bucket")
        )
        # Trunc* returns a date or datetime depending on kind — normalise to a
        # date-string key so the zero-fill loop below can match reliably.
        by_bucket = {}
        for r in rows:
            b = r["bucket"]
            key_str = (b.date() if hasattr(b, "date") else b).isoformat()
            by_bucket[key_str] = r

        series = []
        cursor = _floor_date(timezone.localdate() - timedelta(days=RANGES[key][0]), bucket)
        today = timezone.localdate()
        while cursor <= today:
            hit = by_bucket.get(cursor.isoformat())
            series.append(
                {
                    "date": cursor.isoformat(),
                    "revenue": _money(hit["revenue"]) if hit else 0.0,
                    "orders": hit["orders"] if hit else 0,
                }
            )
            cursor = _floor_date(_next_bucket(cursor, bucket), bucket)

        return Response({"range": key, "bucket": bucket, "series": series})


class TopProductsView(_StaffView):
    """GET /api/v1/admin/reports/top-products/?range=...&limit=10
    Best sellers by units and by revenue over the range."""

    def get(self, request):
        key, start, _ = _resolve_range(request)
        try:
            limit = max(1, min(50, int(request.query_params.get("limit", 10))))
        except ValueError:
            limit = 10

        base = (
            OrderItem.objects.filter(order__status__in=PAID_STATUSES, order__created_at__gte=start)
            .values("product_id", "product_name")
            .annotate(units=Sum("quantity"), revenue=Sum(_line_total))
        )

        def shape(qs):
            return [
                {
                    "product_id": r["product_id"],
                    "name": r["product_name"],
                    "units": r["units"] or 0,
                    "revenue": _money(r["revenue"]),
                }
                for r in qs
            ]

        return Response(
            {
                "range": key,
                "by_units": shape(base.order_by("-units", "-revenue")[:limit]),
                "by_revenue": shape(base.order_by("-revenue", "-units")[:limit]),
            }
        )


class RevenueByBrandView(_StaffView):
    """GET /api/v1/admin/reports/revenue-by-brand/?range=..."""

    def get(self, request):
        key, start, _ = _resolve_range(request)
        rows = (
            OrderItem.objects.filter(order__status__in=PAID_STATUSES, order__created_at__gte=start)
            .values("product__brand_id", "product__brand__name_en")
            .annotate(revenue=Sum(_line_total), units=Sum("quantity"))
            .order_by("-revenue")
        )
        data = [
            {
                "brand_id": r["product__brand_id"],
                "name": r["product__brand__name_en"] or "—",
                "revenue": _money(r["revenue"]),
                "units": r["units"] or 0,
            }
            for r in rows
        ]
        return Response({"range": key, "brands": data})


class RevenueByCategoryView(_StaffView):
    """GET /api/v1/admin/reports/revenue-by-category/?range=...&limit=8"""

    def get(self, request):
        key, start, _ = _resolve_range(request)
        try:
            limit = max(1, min(30, int(request.query_params.get("limit", 8))))
        except ValueError:
            limit = 8
        rows = (
            OrderItem.objects.filter(order__status__in=PAID_STATUSES, order__created_at__gte=start)
            .values("product__category_id", "product__category__name_en")
            .annotate(revenue=Sum(_line_total), units=Sum("quantity"))
            .order_by("-revenue")[:limit]
        )
        data = [
            {
                "category_id": r["product__category_id"],
                "name": r["product__category__name_en"] or "Uncategorised",
                "revenue": _money(r["revenue"]),
                "units": r["units"] or 0,
            }
            for r in rows
        ]
        return Response({"range": key, "categories": data})


class InventoryReportView(_StaffView):
    """GET /api/v1/admin/reports/inventory/
    Total stock value + the actual low/out-of-stock products to act on."""

    def get(self, request):
        active = Product.objects.filter(is_active=True)
        total_value = active.aggregate(
            v=Sum(
                ExpressionWrapper(
                    F("price") * F("stock"),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )
            )
        )["v"]

        low = active.filter(stock__gt=0, stock__lt=LOW_STOCK_THRESHOLD).order_by("stock", "name_en")
        out = active.filter(stock=0).order_by("name_en")

        def shape(qs):
            return [
                {"id": p.id, "sku": p.sku, "name": p.name_en, "stock": p.stock, "price": _money(p.price)}
                for p in qs.only("id", "sku", "name_en", "stock", "price")
            ]

        return Response(
            {
                "total_inventory_value": _money(total_value),
                "active_products": active.count(),
                "low_stock_threshold": LOW_STOCK_THRESHOLD,
                "low_stock_count": low.count(),
                "out_of_stock_count": out.count(),
                "low_stock_products": shape(low),
                "out_of_stock_products": shape(out),
            }
        )


class OrderSummaryView(_StaffView):
    """GET /api/v1/admin/reports/order-summary/?range=...
    AOV, totals and per-status counts for the range."""

    def get(self, request):
        key, start, _ = _resolve_range(request)
        in_range = Order.objects.filter(created_at__gte=start).exclude(status="draft")

        paid_agg = in_range.filter(status__in=PAID_STATUSES).aggregate(
            revenue=Sum("total"), count=Count("id")
        )
        revenue = _money(paid_agg["revenue"])
        paid_count = paid_agg["count"] or 0

        by_status = dict(in_range.values_list("status").annotate(c=Count("id")))

        return Response(
            {
                "range": key,
                "total_orders": in_range.count(),
                "paid_orders": paid_count,
                "total_revenue": revenue,
                "average_order_value": _money(revenue / paid_count) if paid_count else 0.0,
                "orders_by_status": by_status,
            }
        )

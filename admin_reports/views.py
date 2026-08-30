from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from catalog.models import Product
from orders.models import Order


PAID_STATUSES = ["confirmed", "processing", "shipped", "delivered"]
LOW_STOCK_THRESHOLD = 10


def dashboard_stats():
    """Revenue / orders / customers / stock headline numbers. The single source
    of this aggregation — used by both the REST endpoint below and the Django
    Admin index dashboard (admin_reports.dashboard)."""
    last_30_days = timezone.now() - timedelta(days=30)

    revenue_30d = Order.objects.filter(
        status__in=PAID_STATUSES, created_at__gte=last_30_days
    ).aggregate(total=Sum("total"))["total"] or 0

    orders_by_status = dict(
        Order.objects.exclude(status="draft").values_list("status").annotate(count=Count("id"))
    )

    return {
        "revenue_last_30_days": str(revenue_30d),
        "orders_total": Order.objects.exclude(status="draft").count(),
        "orders_by_status": orders_by_status,
        "customers_total": User.objects.filter(is_staff=False).count(),
        "products_total": Product.objects.filter(is_active=True).count(),
        "low_stock_products": Product.objects.filter(
            is_active=True, stock__gt=0, stock__lt=LOW_STOCK_THRESHOLD
        ).count(),
        "out_of_stock_products": Product.objects.filter(is_active=True, stock=0).count(),
    }


class AdminDashboardStatsView(APIView):
    """GET /api/v1/admin/dashboard/ — revenue, orders, customers, products,
    low-stock count. Backs the Admin Dashboard screen from Part 3's spec;
    django admin's list views cover CRUD, this covers the metrics view that
    doesn't fit a table."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(dashboard_stats())

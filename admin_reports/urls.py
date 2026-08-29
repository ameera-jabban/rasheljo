from django.urls import path

from .reports import (
    InventoryReportView,
    OrderSummaryView,
    RevenueByBrandView,
    RevenueByCategoryView,
    SalesOverTimeView,
    TopProductsView,
)
from .views import AdminDashboardStatsView

urlpatterns = [
    path("admin/dashboard/", AdminDashboardStatsView.as_view(), name="admin-dashboard-stats"),
    path("admin/reports/sales-over-time/", SalesOverTimeView.as_view(), name="admin-reports-sales-over-time"),
    path("admin/reports/top-products/", TopProductsView.as_view(), name="admin-reports-top-products"),
    path("admin/reports/revenue-by-brand/", RevenueByBrandView.as_view(), name="admin-reports-revenue-by-brand"),
    path("admin/reports/revenue-by-category/", RevenueByCategoryView.as_view(), name="admin-reports-revenue-by-category"),
    path("admin/reports/inventory/", InventoryReportView.as_view(), name="admin-reports-inventory"),
    path("admin/reports/order-summary/", OrderSummaryView.as_view(), name="admin-reports-order-summary"),
]

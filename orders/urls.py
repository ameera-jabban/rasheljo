from django.urls import path

from .views import OrderConfirmView, OrderCreateFromCartView, OrderDetailView, OrderListView, OrderUpdateDraftView

urlpatterns = [
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/create/", OrderCreateFromCartView.as_view(), name="order-create"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/update/", OrderUpdateDraftView.as_view(), name="order-update-draft"),
    path("orders/<int:pk>/confirm/", OrderConfirmView.as_view(), name="order-confirm"),
]

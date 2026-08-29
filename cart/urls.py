from django.urls import path

from .views import CartApplyCouponView, CartDetailView, CartItemDetailView, CartItemListCreateView

urlpatterns = [
    path("cart/", CartDetailView.as_view(), name="cart-detail"),
    path("cart/items/", CartItemListCreateView.as_view(), name="cart-item-create"),
    path("cart/items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("cart/apply-coupon/", CartApplyCouponView.as_view(), name="cart-apply-coupon"),
]

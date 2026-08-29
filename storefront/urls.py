"""Storefront URLs. Mounted under i18n_patterns in config/urls.py so every path
gets an /en/ or /ar/ prefix, mirroring the React app's /:lang/ routing.

These live only on Django's own port (:8000). The React app (:5173) is a separate
entry point and owns none of these.
"""
from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("search/", views.search, name="search"),
    path("skin-quiz/", views.skin_quiz, name="skin_quiz"),
    path("brands/<slug:slug>/", views.brand_landing, name="brand"),
    path("category/<slug:slug>/", views.category_landing, name="category"),
    path("skin-type/<slug:slug>/", views.skin_type_landing, name="skin_type"),
    path("products/<slug:slug>/", views.product_detail, name="product"),
    path("cart/", views.cart_page, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("account/", views.account, name="account"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("policies/<slug:slug>/", views.policy, name="policy"),

    # htmx fragment endpoints
    path("_/cart/add/", views.cart_add, name="cart_add"),
    path("_/cart/item/<int:item_id>/update/", views.cart_update, name="cart_update"),
    path("_/cart/item/<int:item_id>/remove/", views.cart_remove, name="cart_remove"),
    path("_/wishlist/<int:product_id>/toggle/", views.wishlist_toggle, name="wishlist_toggle"),
]

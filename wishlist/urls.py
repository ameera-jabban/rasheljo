from django.urls import path

from .views import WishlistListView, WishlistToggleView

urlpatterns = [
    path("account/wishlist/", WishlistListView.as_view(), name="wishlist-list"),
    path("account/wishlist/<int:product_id>/", WishlistToggleView.as_view(), name="wishlist-toggle"),
]

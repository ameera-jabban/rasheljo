from django.urls import path

from .views import (
    BrandDetailView,
    BrandListView,
    CategoryDetailView,
    CategoryListView,
    ProductDetailView,
    ProductListView,
    ProductRecommendationsView,
    SearchView,
    SkinTypeListView,
)

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
    path("products/<slug:slug>/recommendations/", ProductRecommendationsView.as_view(), name="product-recommendations"),
    path("brands/", BrandListView.as_view(), name="brand-list"),
    path("brands/<slug:slug>/", BrandDetailView.as_view(), name="brand-detail"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("categories/<slug:slug>/", CategoryDetailView.as_view(), name="category-detail"),
    path("skin-types/", SkinTypeListView.as_view(), name="skin-type-list"),
    path("search/", SearchView.as_view(), name="search"),
]

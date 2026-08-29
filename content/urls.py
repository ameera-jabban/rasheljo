from django.urls import path

from .views import (
    HomepageVideoListView,
    PolicyDetailView,
    PolicyListView,
    SiteSettingsView,
)

urlpatterns = [
    path("homepage-videos/", HomepageVideoListView.as_view(), name="homepage-video-list"),
    path("site-settings/", SiteSettingsView.as_view(), name="site-settings"),
    path("policies/", PolicyListView.as_view(), name="policy-list"),
    path("policies/<slug:slug>/", PolicyDetailView.as_view(), name="policy-detail"),
]

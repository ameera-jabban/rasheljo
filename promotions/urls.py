from django.urls import path

from .views import PromotionDetailView

urlpatterns = [
    path("promotions/<slug:slug>/", PromotionDetailView.as_view(), name="promotion-detail"),
]

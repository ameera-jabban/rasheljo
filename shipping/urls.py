from django.urls import path

from .views import ShippingMethodListView

urlpatterns = [
    path("shipping-methods/", ShippingMethodListView.as_view(), name="shipping-method-list"),
]

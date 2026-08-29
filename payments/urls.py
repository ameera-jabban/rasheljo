from django.urls import path

from .views import PaymentWebhookView

urlpatterns = [
    path("payments/webhook/<str:provider>/", PaymentWebhookView.as_view(), name="payment-webhook"),
]

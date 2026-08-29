from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AddressDetailView,
    AddressListCreateView,
    ForgotPasswordView,
    MeView,
    RegisterView,
    ResetPasswordView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("auth/reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("account/me/", MeView.as_view(), name="account-me"),
    path("account/addresses/", AddressListCreateView.as_view(), name="address-list"),
    path("account/addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
]

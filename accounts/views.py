import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Address
from .serializers import AddressSerializer, RegisterSerializer, UserSerializer

User = get_user_model()
logger = logging.getLogger("accounts.auth")


class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/ — creates the user and returns JWT pair immediately."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=201,
        )


class MeView(APIView):
    """GET/PATCH /api/v1/account/me/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AddressListCreateView(generics.ListCreateAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class ForgotPasswordView(APIView):
    """POST /api/v1/auth/forgot-password/ — always returns 200 regardless of
    whether the email exists, so this endpoint can't be used to enumerate
    registered accounts. The reset email is sent through the shared
    ``notify.tasks.send_password_reset_email`` (fail_silently=False); any SMTP
    error is logged here rather than swallowed."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from notify.tasks import send_password_reset_email

        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and user.email and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            # SITE_URL is env-configurable (defaults to the production domain) so
            # links are correct per environment instead of a hardcoded host. The
            # /en/ prefix matches the SPA's /:lang/reset-password route.
            reset_link = f"{settings.SITE_URL}/en/reset-password?uid={uid}&token={token}"
            try:
                send_password_reset_email(user.id, reset_link, "en")
            except Exception:
                logger.exception("Password-reset email failed to send for user id=%s", user.id)
        return Response({"detail": "If that email exists, a reset link has been sent."})


class ResetPasswordView(APIView):
    """POST /api/v1/auth/reset-password/ — validates the uid/token pair from
    the emailed link and sets the new password."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get("uid", "")
        token = request.data.get("token", "")
        new_password = request.data.get("password", "")

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({"detail": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({"detail": "This reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({"detail": "Password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password has been reset. You can now log in."})

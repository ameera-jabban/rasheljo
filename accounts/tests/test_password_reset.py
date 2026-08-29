import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestPasswordReset:
    def test_forgot_password_always_returns_200(self):
        client = APIClient()
        resp = client.post(reverse("auth-forgot-password"), {"email": "nobody@x.com"})
        assert resp.status_code == 200  # never reveals whether the account exists

    def test_forgot_password_sends_email_for_real_user(self, mailoutbox):
        User.objects.create_user(username="reset@x.com", email="reset@x.com", password="pw12345678!")
        client = APIClient()
        client.post(reverse("auth-forgot-password"), {"email": "reset@x.com"})
        assert len(mailoutbox) == 1
        assert "reset" in mailoutbox[0].subject.lower()

    def test_reset_password_with_valid_token(self):
        user = User.objects.create_user(username="reset2@x.com", email="reset2@x.com", password="oldpassword123")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        client = APIClient()
        resp = client.post(reverse("auth-reset-password"), {"uid": uid, "token": token, "password": "newpassword456"})
        assert resp.status_code == 200

        user.refresh_from_db()
        assert user.check_password("newpassword456")

    def test_reset_password_with_invalid_token_rejected(self):
        user = User.objects.create_user(username="reset3@x.com", email="reset3@x.com", password="oldpassword123")
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        client = APIClient()
        resp = client.post(reverse("auth-reset-password"), {"uid": uid, "token": "garbage", "password": "newpassword456"})
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.check_password("oldpassword123")

    def test_reset_password_too_short_rejected(self):
        user = User.objects.create_user(username="reset4@x.com", email="reset4@x.com", password="oldpassword123")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        client = APIClient()
        resp = client.post(reverse("auth-reset-password"), {"uid": uid, "token": token, "password": "123"})
        assert resp.status_code == 400

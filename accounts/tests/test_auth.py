import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


class TestRegistration:
    def test_register_creates_user_and_returns_tokens(self, client):
        resp = client.post(reverse("auth-register"), {
            "email": "new@example.com", "password": "SuperSecure123!", "first_name": "Jane",
        })
        assert resp.status_code == 201
        assert resp.data["user"]["email"] == "new@example.com"
        assert "access" in resp.data and "refresh" in resp.data

    def test_duplicate_email_rejected(self, client):
        User.objects.create_user(username="dup@x.com", email="dup@x.com", password="pw12345678!")
        resp = client.post(reverse("auth-register"), {
            "email": "dup@x.com", "password": "SuperSecure123!",
        })
        assert resp.status_code == 400

    def test_weak_password_rejected(self, client):
        resp = client.post(reverse("auth-register"), {
            "email": "weak@x.com", "password": "123",
        })
        assert resp.status_code == 400


class TestLogin:
    def test_login_with_correct_credentials(self, client):
        User.objects.create_user(username="login@x.com", email="login@x.com", password="pw12345678!")
        resp = client.post(reverse("auth-login"), {"username": "login@x.com", "password": "pw12345678!"})
        assert resp.status_code == 200
        assert "access" in resp.data

    def test_login_with_wrong_password_rejected(self, client):
        User.objects.create_user(username="login2@x.com", email="login2@x.com", password="pw12345678!")
        resp = client.post(reverse("auth-login"), {"username": "login2@x.com", "password": "wrong"})
        assert resp.status_code == 401


class TestAddresses:
    def test_unauthenticated_cannot_list_addresses(self, client):
        resp = client.get(reverse("address-list"))
        assert resp.status_code == 401

    def test_authenticated_can_create_and_list_own_address(self, client):
        user = User.objects.create_user(username="addr@x.com", email="addr@x.com", password="pw12345678!")
        client.force_authenticate(user=user)
        client.post(reverse("address-list"), {
            "name": "Home", "phone": "0776661237", "city": "Amman", "address_line": "Rainbow St",
        })
        resp = client.get(reverse("address-list"))
        assert resp.data["count"] == 1 if isinstance(resp.data, dict) else len(resp.data) == 1

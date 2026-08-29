import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


class TestHealthCheck:
    def test_health_check_returns_ok_when_dependencies_up(self):
        client = APIClient()
        resp = client.get(reverse("health-check"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["checks"]["database"] == "ok"

    def test_health_check_does_not_require_auth(self):
        client = APIClient()
        resp = client.get(reverse("health-check"))
        assert resp.status_code != 401
        assert resp.status_code != 403

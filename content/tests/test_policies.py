import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from content.models import Policy

pytestmark = pytest.mark.django_db
User = get_user_model()

EXPECTED_SLUGS = {"privacy-policy", "terms-conditions", "return-policy", "shipping-policy"}


@pytest.fixture
def staff_client():
    staff = User.objects.create_user(
        username="admin@x.com", email="admin@x.com", password="pw12345678!", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    return client


@pytest.fixture
def customer_client():
    customer = User.objects.create_user(
        username="cust@x.com", email="cust@x.com", password="pw12345678!"
    )
    client = APIClient()
    client.force_authenticate(user=customer)
    return client


class TestPolicyDefaults:
    def test_four_expected_policies_exist_after_migration(self):
        assert set(Policy.objects.values_list("slug", flat=True)) >= EXPECTED_SLUGS

    def test_default_policies_have_empty_body(self):
        for slug in EXPECTED_SLUGS:
            p = Policy.objects.get(slug=slug)
            assert p.body_en == "" and p.body_ar == ""
            assert p.is_active is True


class TestPolicyPublicEndpoints:
    def test_list_returns_only_active_slug_and_title(self):
        Policy.objects.filter(slug="return-policy").update(is_active=False)
        resp = APIClient().get(reverse("policy-list"))
        assert resp.status_code == 200
        slugs = {row["slug"] for row in resp.data}
        assert "privacy-policy" in slugs
        assert "return-policy" not in slugs  # inactive excluded
        assert set(resp.data[0].keys()) == {"slug", "title_en", "title_ar"}  # no body

    def test_list_needs_no_auth(self):
        assert APIClient().get(reverse("policy-list")).status_code == 200

    def test_detail_returns_full_policy(self):
        Policy.objects.filter(slug="privacy-policy").update(
            body_en="We respect your privacy.", title_ar="سياسة الخصوصية"
        )
        resp = APIClient().get(reverse("policy-detail", kwargs={"slug": "privacy-policy"}))
        assert resp.status_code == 200
        assert resp.data["body_en"] == "We respect your privacy."
        assert resp.data["title_ar"] == "سياسة الخصوصية"
        assert "updated_at" in resp.data

    def test_detail_404_for_unknown_slug(self):
        assert APIClient().get(reverse("policy-detail", kwargs={"slug": "no-such-policy"})).status_code == 404

    def test_detail_404_for_inactive_policy(self):
        Policy.objects.filter(slug="terms-conditions").update(is_active=False)
        assert APIClient().get(reverse("policy-detail", kwargs={"slug": "terms-conditions"})).status_code == 404


class TestPolicyAdminCRUD:
    def test_non_staff_forbidden(self, customer_client):
        assert customer_client.get(reverse("admin-policy-list")).status_code == 403

    def test_unauthenticated_forbidden(self):
        assert APIClient().get(reverse("admin-policy-list")).status_code in (401, 403)

    def test_staff_can_list(self, staff_client):
        resp = staff_client.get(reverse("admin-policy-list"))
        assert resp.status_code == 200
        assert resp.data["count"] == 4

    def test_staff_can_edit_body(self, staff_client):
        policy = Policy.objects.get(slug="privacy-policy")
        resp = staff_client.patch(
            reverse("admin-policy-detail", kwargs={"pk": policy.id}),
            {"body_en": "Draft privacy text.", "body_ar": "نص تجريبي."},
            format="json",
        )
        assert resp.status_code == 200
        policy.refresh_from_db()
        assert policy.body_en == "Draft privacy text."
        assert policy.body_ar == "نص تجريبي."

    def test_staff_can_create_extra_policy(self, staff_client):
        resp = staff_client.post(
            reverse("admin-policy-list"),
            {"slug": "cookie-policy", "title_en": "Cookie Policy"},
            format="json",
        )
        assert resp.status_code == 201
        assert Policy.objects.filter(slug="cookie-policy").exists()

    def test_staff_can_delete_policy(self, staff_client):
        policy = Policy.objects.create(slug="temp-policy", title_en="Temp")
        resp = staff_client.delete(reverse("admin-policy-detail", kwargs={"pk": policy.id}))
        assert resp.status_code == 204
        assert not Policy.objects.filter(slug="temp-policy").exists()

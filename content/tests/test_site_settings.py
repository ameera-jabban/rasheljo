import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from content.models import SiteSettings

pytestmark = pytest.mark.django_db
User = get_user_model()

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


class TestSiteSettingsSingleton:
    def test_load_creates_row_once(self):
        first = SiteSettings.load()
        second = SiteSettings.load()
        assert first.pk == second.pk == 1
        assert SiteSettings.objects.count() == 1

    def test_saving_a_new_instance_overwrites_the_singleton(self):
        SiteSettings.load()
        extra = SiteSettings(site_name="Second")
        extra.save()
        assert SiteSettings.objects.count() == 1
        assert SiteSettings.objects.get().site_name == "Second"

    def test_delete_is_a_noop(self):
        obj = SiteSettings.load()
        obj.delete()
        assert SiteSettings.objects.count() == 1


class TestSiteSettingsPublicEndpoint:
    def test_returns_single_object_without_auth(self):
        resp = APIClient().get(reverse("site-settings"))
        assert resp.status_code == 200
        assert isinstance(resp.data, dict)
        assert "site_name" in resp.data

    def test_blank_copyright_is_returned_empty_for_frontend_fallback(self):
        settings = SiteSettings.load()
        settings.site_name = "Dr Rashel Jo"
        settings.copyright_text_en = ""
        settings.save()

        resp = APIClient().get(reverse("site-settings"))
        assert resp.data["copyright_text_en"] == ""
        assert resp.data["site_name"] == "Dr Rashel Jo"  # frontend builds the line from this


class TestSiteSettingsAdmin:
    def test_non_staff_cannot_read_or_update(self, customer_client):
        assert customer_client.get(reverse("admin-site-settings")).status_code == 403
        assert customer_client.patch(
            reverse("admin-site-settings"), {"site_name": "Hacked"}, format="json"
        ).status_code == 403

    def test_staff_can_update(self, staff_client):
        resp = staff_client.patch(
            reverse("admin-site-settings"),
            {"about_text_en": "Authentic skincare.", "instagram_url": "https://instagram.com/drrashel"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["about_text_en"] == "Authentic skincare."
        assert SiteSettings.objects.get().instagram_url == "https://instagram.com/drrashel"

    def test_staff_update_does_not_create_extra_rows(self, staff_client):
        staff_client.patch(reverse("admin-site-settings"), {"site_name": "A"}, format="json")
        staff_client.patch(reverse("admin-site-settings"), {"site_name": "B"}, format="json")
        assert SiteSettings.objects.count() == 1

    def test_staff_can_upload_logo(self, staff_client):
        resp = staff_client.patch(
            reverse("admin-site-settings"),
            {"logo": SimpleUploadedFile("logo.png", PNG_1PX, content_type="image/png")},
            format="multipart",
        )
        assert resp.status_code == 200, resp.data
        assert SiteSettings.objects.get().logo.name.startswith("site/")

    def test_admin_has_no_list_create_delete(self, staff_client):
        # singleton view — only GET / PATCH
        assert staff_client.post(reverse("admin-site-settings"), {}, format="json").status_code == 405
        assert staff_client.delete(reverse("admin-site-settings")).status_code == 405

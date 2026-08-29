import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from content.models import HomepageVideo

pytestmark = pytest.mark.django_db
User = get_user_model()

TINY_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


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


class TestHomepageVideoModelValidation:
    def test_active_with_neither_source_is_invalid(self):
        video = HomepageVideo(slot="hero", is_active=True)
        with pytest.raises(ValidationError):
            video.full_clean()

    def test_active_with_both_sources_is_invalid(self):
        video = HomepageVideo(
            slot="hero",
            is_active=True,
            video_url="https://cdn.example.com/hero.mp4",
            video_file=SimpleUploadedFile("hero.mp4", TINY_MP4, content_type="video/mp4"),
        )
        with pytest.raises(ValidationError):
            video.full_clean()

    def test_active_with_only_url_is_valid(self):
        video = HomepageVideo(slot="hero", is_active=True, video_url="https://cdn.example.com/hero.mp4")
        video.full_clean()  # should not raise

    def test_active_with_only_file_is_valid(self):
        video = HomepageVideo(
            slot="section_1",
            is_active=True,
            video_file=SimpleUploadedFile("s1.mp4", TINY_MP4, content_type="video/mp4"),
        )
        video.full_clean()  # should not raise

    def test_inactive_draft_skips_source_validation(self):
        video = HomepageVideo(slot="hero", is_active=False)
        video.full_clean()  # a draft with no source is allowed


class TestHomepageVideoPublicEndpoint:
    def test_returns_only_active_rows(self):
        HomepageVideo.objects.create(slot="hero", is_active=True, video_url="https://x/active.mp4")
        HomepageVideo.objects.create(slot="section_1", is_active=False, video_url="https://x/hidden.mp4")

        resp = APIClient().get(reverse("homepage-video-list"))
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["slot"] == "hero"

    def test_ordered_by_slot_then_sort_order(self):
        HomepageVideo.objects.create(slot="section_1", sort_order=2, video_url="https://x/b.mp4")
        HomepageVideo.objects.create(slot="section_1", sort_order=1, video_url="https://x/a.mp4")
        HomepageVideo.objects.create(slot="hero", sort_order=0, video_url="https://x/hero.mp4")

        resp = APIClient().get(reverse("homepage-video-list"))
        order = [(r["slot"], r["sort_order"]) for r in resp.data]
        assert order == [("hero", 0), ("section_1", 1), ("section_1", 2)]

    def test_no_auth_required(self):
        resp = APIClient().get(reverse("homepage-video-list"))
        assert resp.status_code == 200

    def test_video_src_prefers_file_then_url(self):
        HomepageVideo.objects.create(slot="hero", video_url="https://cdn.example.com/hero.mp4")
        resp = APIClient().get(reverse("homepage-video-list"))
        assert resp.data[0]["video_src"] == "https://cdn.example.com/hero.mp4"


class TestHomepageVideoAdminCRUD:
    def test_non_staff_forbidden(self, customer_client):
        assert customer_client.get(reverse("admin-homepage-video-list")).status_code == 403

    def test_unauthenticated_forbidden(self):
        assert APIClient().get(reverse("admin-homepage-video-list")).status_code in (401, 403)

    def test_staff_can_create_with_url(self, staff_client):
        resp = staff_client.post(
            reverse("admin-homepage-video-list"),
            {"slot": "hero", "video_url": "https://cdn.example.com/hero.mp4", "title_en": "Welcome"},
        )
        assert resp.status_code == 201, resp.data
        assert HomepageVideo.objects.count() == 1

    def test_staff_create_active_with_neither_source_rejected(self, staff_client):
        resp = staff_client.post(
            reverse("admin-homepage-video-list"), {"slot": "hero", "is_active": True}, format="json"
        )
        assert resp.status_code == 400

    def test_staff_create_active_with_both_sources_rejected(self, staff_client):
        resp = staff_client.post(
            reverse("admin-homepage-video-list"),
            {
                "slot": "hero",
                "is_active": "true",
                "video_url": "https://cdn.example.com/hero.mp4",
                "video_file": SimpleUploadedFile("hero.mp4", TINY_MP4, content_type="video/mp4"),
            },
            format="multipart",
        )
        assert resp.status_code == 400

    def test_cannot_activate_a_draft_that_has_both_sources(self, staff_client):
        # A messy draft can be saved while inactive, but not switched on as-is.
        video = HomepageVideo.objects.create(
            slot="hero",
            is_active=False,
            video_url="https://cdn.example.com/hero.mp4",
            video_file=SimpleUploadedFile("hero.mp4", TINY_MP4, content_type="video/mp4"),
        )
        resp = staff_client.patch(
            reverse("admin-homepage-video-detail", kwargs={"pk": video.id}),
            {"is_active": True},
            format="json",
        )
        assert resp.status_code == 400

    def test_staff_can_upload_video_file(self, staff_client):
        resp = staff_client.post(
            reverse("admin-homepage-video-list"),
            {
                "slot": "section_1",
                "video_file": SimpleUploadedFile("promo.mp4", TINY_MP4, content_type="video/mp4"),
            },
            format="multipart",
        )
        assert resp.status_code == 201, resp.data
        assert HomepageVideo.objects.get().video_file.name.startswith("homepage/videos/")

    def test_staff_can_update_and_delete(self, staff_client):
        video = HomepageVideo.objects.create(slot="hero", video_url="https://x/a.mp4")
        upd = staff_client.patch(
            reverse("admin-homepage-video-detail", kwargs={"pk": video.id}),
            {"title_en": "Updated"},
            format="json",
        )
        assert upd.status_code == 200
        assert upd.data["title_en"] == "Updated"

        dele = staff_client.delete(reverse("admin-homepage-video-detail", kwargs={"pk": video.id}))
        assert dele.status_code == 204
        assert HomepageVideo.objects.count() == 0

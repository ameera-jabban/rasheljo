"""Regression: toggling HomepageVideo.is_active / sort_order in the admin must
change the homepage without waiting for the 60s in-process cache TTL."""
import pytest
from django.urls import reverse

from content.models import HomepageVideo
from storefront import services

pytestmark = pytest.mark.django_db


def _home(client):
    return client.get(reverse("storefront:home")).content.decode()


class TestHomepageVideoActiveToggle:
    def test_deactivating_hides_the_video_without_restart(self, client):
        v = HomepageVideo.objects.create(
            slot="section_2", is_active=True, video_url="https://cdn.example.com/s2.mp4"
        )
        assert "s2.mp4" in _home(client)  # primes services._cache

        v.is_active = False
        v.save()  # post_save signal must evict "homepage_videos"

        assert "s2.mp4" not in _home(client)

    def test_reactivating_shows_it_again(self, client):
        v = HomepageVideo.objects.create(
            slot="section_1", is_active=False, video_url="https://cdn.example.com/s1.mp4"
        )
        assert "s1.mp4" not in _home(client)

        v.is_active = True
        v.save()

        assert "s1.mp4" in _home(client)

    def test_sort_order_picks_the_lowest_active_row_per_slot(self, client):
        HomepageVideo.objects.create(
            slot="section_3", is_active=True, sort_order=5, video_url="https://x/late.mp4"
        )
        HomepageVideo.objects.create(
            slot="section_3", is_active=True, sort_order=1, video_url="https://x/early.mp4"
        )
        html = _home(client)
        assert "early.mp4" in html
        assert "late.mp4" not in html

    def test_delete_also_invalidates(self, client):
        v = HomepageVideo.objects.create(
            slot="section_2", is_active=True, video_url="https://x/gone.mp4"
        )
        assert "gone.mp4" in _home(client)
        v.delete()
        assert "gone.mp4" not in _home(client)

    def test_invalidate_helper_drops_the_key(self):
        services._cache["homepage_videos"] = (float("inf"), {"sentinel": True})
        services.invalidate("homepage_videos")
        assert "homepage_videos" not in services._cache

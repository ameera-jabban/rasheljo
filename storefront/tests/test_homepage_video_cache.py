"""Regression: toggling HomepageVideo.is_active / sort_order in the admin must
change the homepage without waiting for the 60s reference-data cache TTL."""
import pytest
from django.core.cache import cache
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
        assert "s2.mp4" in _home(client)  # primes the sf:ref:homepage_videos cache

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

    def test_cached_helper_reads_and_writes_the_shared_cache(self):
        calls = []

        def producer():
            calls.append(1)
            return ["value"]

        assert services._cached("demo_key", producer) == ["value"]
        assert services._cached("demo_key", producer) == ["value"]  # served from cache
        assert len(calls) == 1
        assert cache.get("sf:ref:demo_key") == ["value"]  # namespaced, in shared cache

    def test_invalidate_helper_deletes_the_shared_key(self):
        cache.set("sf:ref:homepage_videos", {"sentinel": True}, 60)
        services.invalidate("homepage_videos")
        assert cache.get("sf:ref:homepage_videos") is None

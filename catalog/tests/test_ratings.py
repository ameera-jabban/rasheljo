import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Product
from catalog.tests.factories import ProductFactory
from reviews.models import Review

pytestmark = pytest.mark.django_db
User = get_user_model()


def review(product, rating, *, approved=True, n=0):
    user = User.objects.create_user(username=f"r{product.id}-{n}@x.com", email=f"r{product.id}-{n}@x.com", password="pw")
    return Review.objects.create(user=user, product=product, rating=rating, is_approved=approved)


@pytest.fixture
def client():
    return APIClient()


class TestRatingAnnotations:
    def test_with_ratings_queryset_annotates_avg_and_count(self):
        p = ProductFactory()
        review(p, 5, n=1)
        review(p, 4, n=2)
        review(p, 3, n=3)
        row = Product.objects.with_ratings().get(id=p.id)
        assert row.review_count == 3
        assert round(float(row.average_rating), 2) == 4.0  # (5+4+3)/3

    def test_unapproved_reviews_excluded_from_both(self):
        p = ProductFactory()
        review(p, 5, n=1)
        review(p, 1, approved=False, n=2)  # hidden by moderation
        row = Product.objects.with_ratings().get(id=p.id)
        assert row.review_count == 1
        assert float(row.average_rating) == 5.0

    def test_product_with_no_reviews_is_null_and_zero(self):
        p = ProductFactory()
        row = Product.objects.with_ratings().get(id=p.id)
        assert row.average_rating is None
        assert row.review_count == 0

    def test_list_endpoint_exposes_real_rating_data(self, client):
        rated = ProductFactory(name_en="Rated one")
        review(rated, 5, n=1)
        review(rated, 4, n=2)
        ProductFactory(name_en="Unrated one")

        resp = client.get(reverse("product-list"))
        by_name = {r["name_en"]: r for r in resp.data["results"]}
        assert by_name["Rated one"]["average_rating"] == 4.5
        assert by_name["Rated one"]["review_count"] == 2
        assert by_name["Unrated one"]["average_rating"] is None
        assert by_name["Unrated one"]["review_count"] == 0

    def test_detail_endpoint_exposes_rating_data(self, client):
        p = ProductFactory()
        review(p, 3, n=1)
        resp = client.get(reverse("product-detail", kwargs={"slug": p.slug}))
        assert resp.data["average_rating"] == 3.0
        assert resp.data["review_count"] == 1

    def test_rating_adds_no_per_row_query(self, client):
        """The annotation must be a single JOIN, so the query count is identical
        whether the page has 3 rated products or 15 — i.e. no N+1."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for i in range(3):
            p = ProductFactory(name_en=f"Small {i}")
            review(p, 5, n=i)

        with CaptureQueriesContext(connection) as small:
            client.get(reverse("product-list"))
        small_n = len(small.captured_queries)

        for i in range(12):
            p = ProductFactory(name_en=f"Big {i}")
            review(p, 4, n=100 + i)

        with CaptureQueriesContext(connection) as big:
            client.get(reverse("product-list"))
        big_n = len(big.captured_queries)

        assert big_n == small_n, f"query count grew {small_n} -> {big_n} with more rated products (N+1)"

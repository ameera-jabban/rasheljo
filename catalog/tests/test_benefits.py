import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


class TestBenefitsList:
    def test_benefits_split_into_list(self):
        product = ProductFactory(benefits_en="Brightens skin\nImproves elasticity\nNourishes deeply")
        assert product.benefits_list("en") == ["Brightens skin", "Improves elasticity", "Nourishes deeply"]

    def test_blank_lines_stripped(self):
        product = ProductFactory(benefits_en="Line one\n\n\nLine two\n")
        assert product.benefits_list("en") == ["Line one", "Line two"]

    def test_empty_benefits_returns_empty_list(self):
        product = ProductFactory(benefits_en="")
        assert product.benefits_list("en") == []

    def test_arabic_benefits_independent_of_english(self):
        product = ProductFactory(benefits_en="EN one\nEN two", benefits_ar="عربي واحد\nعربي اثنان")
        assert product.benefits_list("ar") == ["عربي واحد", "عربي اثنان"]

    def test_api_returns_both_benefit_lists(self):
        product = ProductFactory(benefits_en="A\nB", benefits_ar="ا\nب")
        resp = APIClient().get(reverse("product-detail", kwargs={"slug": product.slug}))
        assert resp.data["benefits_en_list"] == ["A", "B"]
        assert resp.data["benefits_ar_list"] == ["ا", "ب"]

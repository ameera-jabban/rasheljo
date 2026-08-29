from unittest import mock

import pytest
from django.core.management import call_command

from catalog.models import Brand, Category, ProductAttribute

pytestmark = pytest.mark.django_db


class FakeTranslator:
    """Stand-in for deep-translator engines — deterministic, no network."""

    def __init__(self, *args, **kwargs):
        pass

    def translate(self, text):
        return f"[ar] {text}"


@pytest.fixture(autouse=True)
def _patch_translators():
    with mock.patch("deep_translator.GoogleTranslator", FakeTranslator), mock.patch(
        "deep_translator.MyMemoryTranslator", FakeTranslator
    ):
        yield


def _run(**kwargs):
    call_command("translate_missing_arabic", sleep=0, **kwargs)


class TestTranslateMissingArabic:
    def test_fills_blank_category_name_and_flags_it(self):
        cat = Category.objects.create(name_en="Face Serums", slug="face-serums", name_ar="")
        _run()
        cat.refresh_from_db()
        assert cat.name_ar == "[ar] Face Serums"
        assert cat.ar_machine_translated is True

    def test_leaves_existing_arabic_untouched(self):
        cat = Category.objects.create(
            name_en="Cleansers", slug="cleansers", name_ar="منظفات"
        )
        _run()
        cat.refresh_from_db()
        assert cat.name_ar == "منظفات"
        assert cat.ar_machine_translated is False

    def test_translates_description_when_name_already_set(self):
        cat = Category.objects.create(
            name_en="Toner", slug="toner", name_ar="تونر",
            description_en="Balances the skin.", description_ar="",
        )
        _run()
        cat.refresh_from_db()
        assert cat.name_ar == "تونر"  # untouched
        assert cat.description_ar == "[ar] Balances the skin."
        assert cat.ar_machine_translated is True

    def test_dry_run_writes_nothing(self):
        cat = Category.objects.create(name_en="Masks", slug="masks", name_ar="")
        _run(dry_run=True)
        cat.refresh_from_db()
        assert cat.name_ar == ""
        assert cat.ar_machine_translated is False

    def test_attribute_values_translated(self):
        attr = ProductAttribute.objects.create(
            attribute_type="skin_type", value_en="Oily Skin", slug="oily-skin", value_ar=""
        )
        _run(models="attribute")
        attr.refresh_from_db()
        assert attr.value_ar == "[ar] Oily Skin"
        assert attr.ar_machine_translated is True

    def test_models_option_scopes_the_run(self):
        cat = Category.objects.create(name_en="Gifts", slug="gifts", name_ar="")
        brand = Brand.objects.create(name_en="NewBrand", slug="newbrand", name_ar="")
        _run(models="brand")
        cat.refresh_from_db()
        brand.refresh_from_db()
        assert cat.name_ar == ""  # category not in scope
        assert brand.name_ar == "[ar] NewBrand"

    def test_limit_caps_rows(self):
        for i in range(5):
            Category.objects.create(name_en=f"Cat {i}", slug=f"cat-{i}", name_ar="")
        _run(limit=2)
        assert Category.objects.filter(ar_machine_translated=True).count() == 2

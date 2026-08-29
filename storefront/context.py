"""Request-level context shared by every storefront template — the Django-side
equivalent of the React app's always-mounted providers (LanguageContext,
useSiteSettings, useCart in the header)."""
from __future__ import annotations

from django.utils.translation import get_language

from storefront.i18n import normalize_lang
from storefront.services import cart_badge_count, get_site_settings


def storefront(request):
    lang = normalize_lang(get_language())
    return {
        "lang": lang,
        "dir": "rtl" if lang == "ar" else "ltr",
        "is_ar": lang == "ar",
        "other_lang": "en" if lang == "ar" else "ar",
        "site_settings": get_site_settings(),
        "cart_count": cart_badge_count(request),
    }

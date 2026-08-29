"""Template helpers for the Django-templates storefront.

Kept deliberately small: a translation tag that reads the ported i18next catalog,
a language-variant picker mirroring ``frontend/src/lib/i18n-helpers.ts``, and a
price formatter mirroring ``frontend/src/lib/currency``.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template
from django.urls import translate_url
from django.utils.safestring import mark_safe
from django.utils.translation import get_language

from storefront.i18n import normalize_lang, translate
from storefront.services import BADGE_LABEL_KEYS, primary_image_url

register = template.Library()


@register.simple_tag
def t(key, **params):
    """{% t "home.hotOffers" %} · {% t "product.lowStock" count=3 %}"""
    return translate(key, **params)


@register.simple_tag
def tjson(*keys):
    """Marks a translated string safe for embedding in a JS string literal."""
    import json

    return mark_safe(json.dumps({k: translate(k) for k in keys}))


@register.filter
def localized(entity, field="name"):
    """``{{ brand|localized }}`` → name_ar when the active language is Arabic and
    it's non-empty, else name_en. ``{{ attr|localized:"value" }}`` for
    ProductAttribute (value_en/value_ar)."""
    if entity is None:
        return ""
    lang = normalize_lang(get_language())
    en = getattr(entity, f"{field}_en", "") or ""
    ar = getattr(entity, f"{field}_ar", "") or ""
    return ar if (lang == "ar" and ar) else en


@register.filter
def money(amount):
    """Mirrors the storefront price format: ``JOD 8.80`` in English, ``8.80 د.أ``
    in Arabic. Always wrap the output in a ``.price`` element in the template so
    it stays LTR inside RTL text."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        return ""
    formatted = f"{value:.2f}"
    if normalize_lang(get_language()) == "ar":
        return f"{formatted} د.أ"
    return f"JOD {formatted}"


@register.filter
def primary_image(product):
    """URL of a product's first image (by sort_order), or '' — mirrors
    ProductListSerializer.get_primary_image."""
    return primary_image_url(product) or ""


@register.simple_tag
def badge_label(badge_type):
    key = BADGE_LABEL_KEYS.get(badge_type)
    return translate(key) if key else ""


_RIBBON_BG = {
    "bestseller": "bg-[var(--color-brand-secondary)]",
    "new_arrival": "bg-[var(--color-ink)]",
    "hot_offer": "bg-[var(--color-sale)]",
    "last_chance": "bg-[var(--color-sale)]",
    "set": "bg-[var(--color-brand-primary)]",
}


@register.simple_tag
def badge_context(badge_type, size="sm"):
    """All computed geometry/typography for the corner ribbon — ports the maths
    in Badge.tsx so the template stays declarative."""
    lang = normalize_lang(get_language())
    is_ar = lang == "ar"
    label = translate(BADGE_LABEL_KEYS.get(badge_type, "")) if badge_type else ""
    n = len(label.strip())
    lg = size == "lg"
    d = 36 if lg else 24
    wrap_px = 124 if lg else 84

    if lg:
        font = "text-xs" if n <= 5 else ("text-[11px]" if n <= 10 else "text-[10px]")
    else:
        font = "text-[10px]" if n <= 5 else ("text-[9px]" if n <= 10 else "text-[8px]")

    tracking = "tracking-normal" if is_ar else ("tracking-tight" if n > 8 else "tracking-wide")

    return {
        "label": label,
        "bg": _RIBBON_BG.get(badge_type, ""),
        "wrap": "h-[124px] w-[124px]" if lg else "h-[84px] w-[84px]",
        "band": "w-[150px] py-1" if lg else "w-[104px] py-[3px]",
        "font": font,
        "tracking": tracking,
        "top": d,
        "left": (wrap_px - d) if is_ar else d,
    }


@register.simple_tag(takes_context=True)
def switch_language_url(context, target_lang):
    """Current page URL under the other language prefix (/en/… ↔ /ar/…)."""
    request = context.get("request")
    path = request.get_full_path() if request else "/"
    try:
        return translate_url(path, target_lang)
    except Exception:
        return f"/{target_lang}/"


@register.filter
def dictkey(mapping, key):
    """``{{ some_dict|dictkey:variable }}`` — lookup with a dynamic key."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None

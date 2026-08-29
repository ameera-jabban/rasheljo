"""Dict-based translation for the Django-templates storefront.

The strings live in ``storefront/i18n/{en,ar}.json`` — byte-for-byte copies of the
React app's ``frontend/src/i18n/*.json`` so the two frontends never drift. We keep
i18next's dotted keys (``"home.hotOffers"``) and ``{{var}}`` interpolation syntax
so the copy is mechanical.

Django's ``i18n_patterns`` / ``LocaleMiddleware`` still own the URL prefix and the
active language; this module only turns a key into a string.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from django.utils.translation import get_language

_I18N_DIR = Path(__file__).resolve().parent / "i18n"
_SUPPORTED = ("en", "ar")
_INTERP = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@lru_cache(maxsize=None)
def _catalog(lang: str) -> dict:
    path = _I18N_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _lookup(catalog: dict, key: str):
    node = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def normalize_lang(lang: str | None) -> str:
    if lang and lang.split("-")[0] in _SUPPORTED:
        return lang.split("-")[0]
    return "en"


def translate(key: str, lang: str | None = None, **params) -> str:
    """Resolve ``key`` for ``lang`` (defaults to the active request language),
    falling back to English and finally to the key itself. ``{{var}}`` tokens are
    filled from ``params``."""
    lang = normalize_lang(lang or get_language())
    value = _lookup(_catalog(lang), key)
    if value is None and lang != "en":
        value = _lookup(_catalog("en"), key)
    if value is None:
        return key

    if params:
        value = _INTERP.sub(lambda m: str(params.get(m.group(1), m.group(0))), value)
    return value


def all_strings(lang: str | None = None) -> dict:
    """The whole catalog for a language — handy for a JSON blob consumed by
    Alpine components that need client-side copy."""
    return _catalog(normalize_lang(lang or get_language()))

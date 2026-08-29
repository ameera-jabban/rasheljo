"""robots.txt and a multilingual XML sitemap for the storefront.

The storefront is a client-rendered SPA served from SITE_URL; these two routes
give crawlers a stable, server-rendered map of every indexable URL (homepage,
shop, brand, category, skin-type and product pages) in both languages, with
hreflang alternates. Private/transactional routes are excluded.
"""
from django.conf import settings
from django.http import HttpResponse
from django.utils.xmlutils import SimplerXMLGenerator
from io import StringIO

from catalog.models import Brand, Category, Product

SKIN_TYPE_SLUGS = ["oily-skin", "dry-skin", "sensitive-skin", "uneven-skin", "combination-skin"]

DISALLOW = [
    "/*/cart",
    "/*/checkout",
    "/*/account",
    "/*/login",
    "/*/register",
    "/*/forgot-password",
    "/*/reset-password",
    "/*/search",
    "/admin/",
    "/api/",
]


def robots_txt(request):
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {path}" for path in DISALLOW]
    lines += ["", f"Sitemap: {settings.SITE_URL}/sitemap.xml", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def _bare_paths():
    """Yield (bare_path, changefreq, priority) for every indexable page."""
    yield ("/", "daily", "1.0")
    yield ("/shop", "daily", "0.9")
    for slug in SKIN_TYPE_SLUGS:
        yield (f"/skin-type/{slug}", "weekly", "0.5")
    for slug in Brand.objects.filter(is_active=True).values_list("slug", flat=True):
        yield (f"/brands/{slug}", "weekly", "0.7")
    for slug in (
        Category.objects.filter(is_active=True)
        .order_by("slug")
        .values_list("slug", flat=True)
    ):
        yield (f"/category/{slug}", "weekly", "0.7")
    for slug in (
        Product.objects.filter(is_active=True)
        .order_by("-updated_at")
        .values_list("slug", flat=True)
    ):
        yield (f"/products/{slug}", "weekly", "0.8")


def _abs(lang, bare):
    tail = "" if bare == "/" else bare
    return f"{settings.SITE_URL}/{lang}{tail}"


def sitemap_xml(request):
    langs = settings.SITE_LANGS
    out = StringIO()
    xml = SimplerXMLGenerator(out, "utf-8")
    xml.startDocument()
    xml.startElement(
        "urlset",
        {
            "xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9",
            "xmlns:xhtml": "http://www.w3.org/1999/xhtml",
        },
    )

    for bare, changefreq, priority in _bare_paths():
        for lang in langs:
            xml.startElement("url", {})
            xml.addQuickElement("loc", _abs(lang, bare))
            for alt in langs:
                xml.addQuickElement(
                    "xhtml:link",
                    "",
                    {"rel": "alternate", "hreflang": alt, "href": _abs(alt, bare)},
                )
            xml.addQuickElement(
                "xhtml:link",
                "",
                {"rel": "alternate", "hreflang": "x-default", "href": _abs("en", bare)},
            )
            xml.addQuickElement("changefreq", changefreq)
            xml.addQuickElement("priority", priority)
            xml.endElement("url")

    xml.endElement("urlset")
    xml.endDocument()
    return HttpResponse(out.getvalue(), content_type="application/xml")

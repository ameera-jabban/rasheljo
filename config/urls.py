from django.contrib import admin
from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.urls import include, path, re_path
from django.views.static import serve

from .health import health_check
from .seo import robots_txt, sitemap_xml

# Non-localized: the DRF API and Django admin keep their exact existing paths.
# The React app (./frontend, :5173) is a separate entry point and owns none of
# these — nothing here intercepts or redirects a route it uses.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap-xml"),
    path("i18n/", include("django.conf.urls.i18n")),  # set_language endpoint
    path("api/v1/health/", health_check, name="health-check"),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("content.urls")),
    path("api/v1/", include("cart.urls")),
    path("api/v1/", include("orders.urls")),
    path("api/v1/", include("wishlist.urls")),
    path("api/v1/", include("reviews.urls")),
    path("api/v1/", include("promotions.urls")),
    path("api/v1/", include("shipping.urls")),
    path("api/v1/", include("admin_reports.urls")),
    path("api/v1/", include("admin_api.urls")),
    path("api/v1/", include("payments.urls")),
]

# Localized Django-templates storefront: /en/… and /ar/… (bare / → /en/).
urlpatterns += i18n_patterns(
    path("", include("storefront.urls")),
    prefix_default_language=True,
)

# Serve user-uploaded media (product images, homepage videos, site logo) in every
# environment, not just DEBUG. Django's built-in `static()` helper returns nothing
# when DEBUG=False, which is why media 404s in production and forced DEBUG=True as
# a workaround — a far worse trade (stack traces + settings exposed on any error).
#
# `django.views.static.serve` is Django-documented as NOT for high-traffic use:
# it's synchronous, unbuffered, and sets no cache headers. It's an acceptable
# stopgap at this project's current traffic, NOT a long-term answer. The planned
# fix is a dedicated storage backend (django-storages → Cloudflare R2 / S3; the
# hook already exists in config/settings_production.py behind MEDIA_STORAGE_BACKEND),
# after which this route should be removed.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

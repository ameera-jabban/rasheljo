from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from .health import health_check
from .seo import robots_txt, sitemap_xml

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap-xml"),
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

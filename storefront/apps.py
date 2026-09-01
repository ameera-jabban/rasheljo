from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storefront"
    verbose_name = "Storefront (Django templates)"

    def ready(self):
        from storefront import signals  # noqa: F401  (registers cache-invalidation receivers)

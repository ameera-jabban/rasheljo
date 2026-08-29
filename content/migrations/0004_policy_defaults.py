from django.db import migrations

# The four policy pages the storefront footer links to. Seeded with EMPTY body
# text — the rows exist so an admin has something to fill in immediately; the
# actual legal copy is written by the business, not fabricated here.
DEFAULTS = [
    ("privacy-policy", "Privacy Policy"),
    ("terms-conditions", "Terms & Conditions"),
    ("return-policy", "Return Policy"),
    ("shipping-policy", "Shipping Policy"),
]


def create_default_policies(apps, schema_editor):
    Policy = apps.get_model("content", "Policy")
    for slug, title_en in DEFAULTS:
        Policy.objects.get_or_create(
            slug=slug,
            defaults={"title_en": title_en, "is_active": True},
        )


def remove_default_policies(apps, schema_editor):
    Policy = apps.get_model("content", "Policy")
    Policy.objects.filter(slug__in=[s for s, _ in DEFAULTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0003_policy"),
    ]

    operations = [
        migrations.RunPython(create_default_policies, remove_default_policies),
    ]

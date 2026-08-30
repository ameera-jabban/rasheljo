from django.db import migrations

# Arabic titles for the footer policy pages. These are short UI labels, not legal
# content — the body text stays empty (still waiting on business-provided copy).
# Only fills rows where title_ar is still blank, so an admin edit is never
# overwritten.
TITLES_AR = {
    "privacy-policy": "سياسة الخصوصية",
    "terms-conditions": "الشروط والأحكام",
    "return-policy": "سياسة الإرجاع",
    "shipping-policy": "سياسة الشحن",
}


def fill_titles_ar(apps, schema_editor):
    Policy = apps.get_model("content", "Policy")
    for slug, title_ar in TITLES_AR.items():
        Policy.objects.filter(slug=slug, title_ar="").update(title_ar=title_ar)


def clear_titles_ar(apps, schema_editor):
    Policy = apps.get_model("content", "Policy")
    for slug, title_ar in TITLES_AR.items():
        Policy.objects.filter(slug=slug, title_ar=title_ar).update(title_ar="")


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0004_policy_defaults"),
    ]

    operations = [
        migrations.RunPython(fill_titles_ar, clear_titles_ar),
    ]

from django.db import migrations


def create_singleton(apps, schema_editor):
    SiteSettings = apps.get_model("content", "SiteSettings")
    SiteSettings.objects.get_or_create(pk=1, defaults={"site_name": "Dr Rashel Jo"})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_singleton, noop),
    ]

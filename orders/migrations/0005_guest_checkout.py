import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fill_public_tokens(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(public_token__isnull=True).only("id"):
        order.public_token = uuid.uuid4()
        order.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_order_perf_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="user",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="orders", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        # unique UUID on existing rows: add nullable, backfill, then tighten —
        # a plain AddField would give every old order the same uuid.
        migrations.AddField(
            model_name="order",
            name="public_token",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(fill_public_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="public_token",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]

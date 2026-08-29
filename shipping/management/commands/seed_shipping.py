from django.core.management.base import BaseCommand

from shipping.models import ShippingMethod


class Command(BaseCommand):
    help = "Seed real-world-plausible shipping methods for Jordan."

    def handle(self, *args, **options):
        methods = [
            ("Standard Delivery", "توصيل عادي", "2.50", 2, 4),
            ("Express Delivery", "توصيل سريع", "5.00", 1, 1),
            ("Amman Same-Day", "نفس اليوم - عمان", "4.00", 0, 1),
        ]
        created = 0
        for name_en, name_ar, cost, dmin, dmax in methods:
            _, was_created = ShippingMethod.objects.get_or_create(
                name_en=name_en,
                defaults={"name_ar": name_ar, "cost": cost, "estimated_days_min": dmin, "estimated_days_max": dmax},
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} shipping methods."))

"""Seed a spread of realistic completed orders so the admin Reports page has a
meaningful dataset to chart. The real store currently has almost no order
history — this fills that gap for demos/QA without touching real data.

    python manage.py seed_demo_orders            # ~40 orders over the last 100 days
    python manage.py seed_demo_orders --count 80
    python manage.py seed_demo_orders --wipe     # remove every seeded demo order

All seeded orders belong to a single tagged demo customer
(demo-orders@drrasheljo.local) so --wipe can find and delete exactly them.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from orders.models import Order, OrderItem

User = get_user_model()
DEMO_EMAIL = "demo-orders@drrasheljo.local"
STATUS_WEIGHTS = [
    ("delivered", 55),
    ("shipped", 15),
    ("processing", 12),
    ("confirmed", 10),
    ("cancelled", 5),
    ("pending", 3),
]


class Command(BaseCommand):
    help = "Seed (or wipe) demo orders for the admin Reports page."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=40)
        parser.add_argument("--days", type=int, default=100, help="Spread orders over the last N days.")
        parser.add_argument("--wipe", action="store_true", help="Delete all seeded demo orders and exit.")

    @transaction.atomic
    def handle(self, *args, **opt):
        demo_user, _ = User.objects.get_or_create(
            username=DEMO_EMAIL,
            defaults={"email": DEMO_EMAIL, "first_name": "Demo", "last_name": "Orders", "is_active": False},
        )

        if opt["wipe"]:
            n, _ = Order.objects.filter(user=demo_user).delete()
            self.stdout.write(self.style.SUCCESS(f"Wiped {n} rows for {DEMO_EMAIL}."))
            return

        existing = Order.objects.filter(user=demo_user).count()
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"{existing} demo orders already exist. Run with --wipe first to reseed cleanly."
                )
            )
            return

        products = list(
            Product.objects.filter(is_active=True, stock__gt=0).only("id", "name_en", "price")
        )
        if len(products) < 5:
            self.stderr.write(self.style.ERROR("Not enough active products to seed orders."))
            return

        statuses = [s for s, w in STATUS_WEIGHTS for _ in range(w)]
        now = timezone.now()
        created = 0

        for _ in range(opt["count"]):
            status = random.choice(statuses)
            days_ago = random.randint(0, opt["days"])
            # weight recent days a little more so the trend line slopes up
            days_ago = min(days_ago, random.randint(0, opt["days"]))
            when = now - timedelta(days=days_ago, hours=random.randint(0, 23))

            order = Order.objects.create(
                user=demo_user,
                status=status,
                payment_method=random.choice(["cod", "cod", "card"]),
                shipping_cost=Decimal("2.00"),
            )
            subtotal = Decimal("0.00")
            for product in random.sample(products, random.randint(1, 4)):
                qty = random.randint(1, 3)
                unit = Decimal(str(product.price))
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name_en,
                    unit_price=unit,
                    quantity=qty,
                )
                subtotal += unit * qty

            order.subtotal = subtotal
            order.total = subtotal + order.shipping_cost
            order.save(update_fields=["subtotal", "total"])
            # created_at is auto_now_add — force the historical date.
            Order.objects.filter(pk=order.pk).update(created_at=when, updated_at=when)
            created += 1

        paid = Order.objects.filter(
            user=demo_user, status__in=["confirmed", "processing", "shipped", "delivered"]
        )
        from django.db.models import Sum

        revenue = paid.aggregate(s=Sum("total"))["s"] or 0
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} demo orders ({paid.count()} paid, {revenue:.2f} JOD revenue) "
                f"spread over the last {opt['days']} days."
            )
        )
        self.stdout.write("Undo with:  python manage.py seed_demo_orders --wipe")

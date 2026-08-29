"""
Listens for order status changes without orders.models importing notify at
all — keeps the dependency one-directional per Part 2's architecture note.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from orders.models import OrderStatusHistory


@receiver(post_save, sender=OrderStatusHistory)
def notify_on_status_change(sender, instance, created, **kwargs):
    if not created:
        return
    from .dispatch import enqueue
    from .tasks import send_order_status_update, send_review_request_email

    # This signal fires inside the order-confirm / status-change request, so a
    # broker outage here must not roll back the order — enqueue() swallows it.
    enqueue(send_order_status_update, instance.order_id, instance.to_status)
    if instance.to_status == "delivered":
        enqueue(send_review_request_email, instance.order_id)

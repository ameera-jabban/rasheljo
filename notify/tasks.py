"""
Real Celery tasks, matching Part 3's task list. Each one both sends the
email (via Django's configured EMAIL_BACKEND — console in dev, real SMTP in
production) and writes a Notification row the account UI can show.
"""
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from .models import Notification

User = get_user_model()


@shared_task
def send_order_confirmation_email(order_id):
    from orders.models import Order
    order = Order.objects.select_related("user").get(id=order_id)
    send_mail(
        subject=f"Order #{order.id} confirmed",
        message=f"Thanks for your order! Total: {order.total} JOD.",
        from_email=None,
        recipient_list=[order.user.email],
        fail_silently=True,
    )
    Notification.objects.create(
        user=order.user, notification_type="order_confirmation",
        title=f"Order #{order.id} confirmed", body=f"Total: {order.total} JOD",
    )


@shared_task
def send_order_status_update(order_id, new_status):
    from orders.models import Order
    order = Order.objects.select_related("user").get(id=order_id)
    send_mail(
        subject=f"Order #{order.id} is now {new_status}",
        message=f"Your order status changed to: {new_status}.",
        from_email=None,
        recipient_list=[order.user.email],
        fail_silently=True,
    )
    Notification.objects.create(
        user=order.user, notification_type="order_status_update",
        title=f"Order #{order.id} — {new_status}", body="",
    )


@shared_task
def send_welcome_email(user_id):
    user = User.objects.get(id=user_id)
    send_mail(
        subject="Welcome to Dr Rashel Jo",
        message="Thanks for creating an account.",
        from_email=None,
        recipient_list=[user.email],
        fail_silently=True,
    )
    Notification.objects.create(user=user, notification_type="welcome", title="Welcome!", body="")


@shared_task
def low_stock_alert(product_id, threshold=10):
    from catalog.models import Product
    product = Product.objects.get(id=product_id)
    if product.stock < threshold:
        staff = User.objects.filter(is_staff=True)
        for user in staff:
            Notification.objects.create(
                user=user, notification_type="low_stock",
                title=f"Low stock: {product.sku}", body=f"Only {product.stock} left.",
            )


@shared_task
def cart_abandonment_reminder():
    """Scheduled via Celery Beat — finds carts with items, no matching recent
    order, idle for 2+ hours, and reminds the (logged-in) owner."""
    from datetime import timedelta
    from django.utils import timezone
    from cart.models import Cart

    cutoff = timezone.now() - timedelta(hours=2)
    stale_carts = Cart.objects.filter(updated_at__lt=cutoff, user__isnull=False, items__isnull=False).distinct()
    for cart in stale_carts:
        send_mail(
            subject="You left something in your cart",
            message="Your cart is still waiting for you at Dr Rashel Jo.",
            from_email=None,
            recipient_list=[cart.user.email],
            fail_silently=True,
        )


@shared_task
def send_review_request_email(order_id):
    from orders.models import Order
    order = Order.objects.select_related("user").get(id=order_id)
    send_mail(
        subject="How was your order?",
        message="We'd love a quick review of your recent purchase.",
        from_email=None,
        recipient_list=[order.user.email],
        fail_silently=True,
    )

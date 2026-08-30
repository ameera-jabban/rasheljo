import pytest
from django.contrib.auth import get_user_model

from notify.models import Notification
from notify.tasks import send_password_reset_email

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestPasswordResetEmailTask:
    def _user(self, **kw):
        kw.setdefault("username", "p@x.com")
        kw.setdefault("email", "p@x.com")
        kw.setdefault("password", "pw12345678!")
        return User.objects.create_user(**kw)

    def test_sends_and_records_notification(self, mailoutbox):
        u = self._user()
        url = "https://dr-rasheljo.com/en/reset-password?uid=abc&token=def-123"
        send_password_reset_email(u.id, url, "en")

        assert len(mailoutbox) == 1
        msg = mailoutbox[0]
        assert "reset" in msg.subject.lower()
        assert url in msg.body
        assert msg.to == ["p@x.com"]
        assert Notification.objects.filter(user=u, notification_type="password_reset").exists()

    def test_arabic_copy(self, mailoutbox):
        u = self._user(username="p2@x.com", email="p2@x.com")
        send_password_reset_email(u.id, "https://dr-rasheljo.com/ar/reset-password?uid=a&token=b", "ar")
        msg = mailoutbox[0]
        assert "كلمة المرور" in msg.subject
        assert "reset-password" in msg.body

    def test_smtp_failure_is_not_swallowed(self, settings, mailoutbox):
        """fail_silently=False: a dead SMTP host must raise, not vanish."""
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = "127.0.0.1"
        settings.EMAIL_PORT = 1  # nothing listens here
        settings.EMAIL_TIMEOUT = 2
        u = self._user(username="p3@x.com", email="p3@x.com")
        with pytest.raises(Exception):
            send_password_reset_email(u.id, "https://x/en/reset-password?uid=a&token=b", "en")
        assert not Notification.objects.filter(user=u).exists()

    def test_no_email_address_is_a_noop(self, mailoutbox):
        u = self._user(username="noemail", email="")
        send_password_reset_email(u.id, "https://x/en/reset-password", "en")
        assert len(mailoutbox) == 0

"""
rounds/auth_utils.py — Auth token & email helpers (ported from FundaBiz)

Uses Django's built-in token generator (uidb64 + signed token) for both
email verification and password reset — no custom token model needed.
"""

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


# ─── TOKEN HELPERS ────────────────────────────────────────────────────────────

def generate_uid(user):
    """Return a URL-safe base64 encoding of the user's primary key."""
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uidb64):
    """Decode a uidb64 string back to a user pk string. Returns None on error."""
    try:
        return force_str(urlsafe_base64_decode(uidb64))
    except Exception:
        return None


def get_user_from_uid(uidb64):
    """Resolve a uidb64 to a User instance, or None if invalid."""
    uid = decode_uid(uidb64)
    if uid is None:
        return None
    try:
        # Try UUID first (Mukando uses UUID primary keys)
        import uuid
        return User.objects.get(pk=uuid.UUID(uid))
    except (ValueError, AttributeError):
        pass
    try:
        return User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def make_token(user):
    """Generate a one-use signed token for the given user."""
    return default_token_generator.make_token(user)


def check_token(user, token):
    """Validate that a token is still valid for the given user."""
    return default_token_generator.check_token(user, token)


# ─── EMAIL HELPERS ────────────────────────────────────────────────────────────

def send_verification_email(user, request):
    """
    Send an account-activation email to the newly registered user.
    Account stays is_active=False until this link is followed.
    """
    uid = generate_uid(user)
    token = make_token(user)

    verify_url = request.build_absolute_uri(
        f"/api/auth/verify/{uid}/{token}/"
    )

    subject = "Verify your Mukando account"
    message = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        f"Welcome to Mukando! Please verify your email address by clicking "
        f"the link below:\n\n"
        f"  {verify_url}\n\n"
        f"This link will expire after 24 hours.\n\n"
        f"If you did not create this account, you can safely ignore this email.\n\n"
        f"— The Mukando Team"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def send_password_reset_email(user, frontend_base_url):
    """
    Send a password-reset link to the user.

    The link targets the frontend reset page, e.g.:
      https://mukando.app/reset-password/<uidb64>/<token>/

    The frontend collects the new password and POSTs to
      /api/auth/reset-password/<uidb64>/<token>/
    """
    uid = generate_uid(user)
    token = make_token(user)

    base = frontend_base_url.rstrip("/")
    reset_url = f"{base}/reset-password/{uid}/{token}/"

    subject = "Reset your Mukando password"
    message = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        f"We received a request to reset the password for your Mukando account.\n\n"
        f"Click the link below to choose a new password:\n\n"
        f"  {reset_url}\n\n"
        f"This link expires after 24 hours and can only be used once.\n\n"
        f"If you did not request a password reset, no action is needed — "
        f"your account is safe.\n\n"
        f"— The Mukando Team"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )
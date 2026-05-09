"""FUNDABIZ — Users Utilities
Token generation, UID encoding, and email dispatch helpers.
All email/token logic lives here so views stay clean.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

User = get_user_model()


# ─── UID Helpers ──────────────────────────────────────────────────────────────

def encode_uid(user) -> str:
    """Return a URL-safe base64 encoding of the user's primary key."""
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uidb64: str):
    """
    Decode a uidb64 string back to a User instance.
    Returns the User on success, or None on any failure.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None


# ─── Email Verification ───────────────────────────────────────────────────────

def send_verification_email(user) -> None:
    """
    Generate a signed verification token and email a confirmation link.
    The link points to the backend API endpoint which activates the account.
    """
    uid = encode_uid(user)
    token = default_token_generator.make_token(user)

    # Backend verification endpoint — the view handles activation directly
    verify_url = (
        f"{settings.BACKEND_URL.rstrip('/')}"
        f"/api/auth/verify-email/{uid}/{token}/"
    )

    subject = "Verify your FUNDABIZ account"
    message = (
        f"Hi {user.first_name or user.email},\n\n"
        f"Welcome to FUNDABIZ! Please verify your email address by clicking the link below:\n\n"
        f"{verify_url}\n\n"
        f"This link will expire in 24 hours. "
        f"If you did not create an account, please ignore this email.\n\n"
        f"— The FUNDABIZ Team"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


# ─── Password Reset ───────────────────────────────────────────────────────────

def send_password_reset_email(user) -> None:
    """
    Generate a signed password-reset token and email a reset link.
    The link points to the frontend, which calls the reset API endpoint.
    Never called if the email doesn't exist — safe by design.
    """
    uid = encode_uid(user)
    token = default_token_generator.make_token(user)

    # Frontend reset page — the frontend then calls /api/auth/reset-password/<uid>/<token>/
    reset_url = (
        f"{settings.FRONTEND_URL.rstrip('/')}"
        f"/reset-password/{uid}/{token}/"
    )

    subject = "Reset your FUNDABIZ password"
    message = (
        f"Hi {user.first_name or user.email},\n\n"
        f"You requested a password reset for your FUNDABIZ account.\n\n"
        f"Click the link below to set a new password:\n\n"
        f"{reset_url}\n\n"
        f"This link will expire in 24 hours. "
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"— The FUNDABIZ Team"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

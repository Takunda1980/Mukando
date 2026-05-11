"""
rounds/auth_utils.py — Auth token & email helpers

Uses Django's built-in token generator (uidb64 + signed token) for both
email verification and password reset.

Emails are sent via Resend HTTP API directly (no SMTP) to avoid Railway
port blocking issues.
"""

import json
import logging
import urllib.request
import urllib.error

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


# ─── TOKEN HELPERS ────────────────────────────────────────────────────────────

def generate_uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uidb64):
    try:
        return force_str(urlsafe_base64_decode(uidb64))
    except Exception:
        return None


def get_user_from_uid(uidb64):
    uid = decode_uid(uidb64)
    if uid is None:
        return None
    try:
        import uuid
        return User.objects.get(pk=uuid.UUID(uid))
    except (ValueError, AttributeError):
        pass
    try:
        return User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def make_token(user):
    return default_token_generator.make_token(user)


def check_token(user, token):
    return default_token_generator.check_token(user, token)


# ─── RESEND HTTP API ──────────────────────────────────────────────────────────

def _send_via_resend(to_email, subject, text_body):
    """Send email via Resend HTTP API — no SMTP, no port issues on Railway."""
    api_key = getattr(settings, 'RESEND_API_KEY', '')

    if not api_key:
        logger.warning(
            "RESEND_API_KEY is not configured — skipping verification email "
            "to %s. Set RESEND_API_KEY in the environment to enable email delivery.",
            to_email,
        )
        return

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'onboarding@resend.dev')

    payload = json.dumps({
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "mukando/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            logger.info("Resend email sent: %s", result.get("id"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        logger.error("Resend API error %s: %s", e.code, error_body)
    except BaseException as e:
        logger.error("Resend send failed: %s", e)


# ─── EMAIL HELPERS ────────────────────────────────────────────────────────────

def send_verification_email(user, request):
    uid = generate_uid(user)
    token = make_token(user)
    verify_url = request.build_absolute_uri(f"/api/auth/verify/{uid}/{token}/")

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
    _send_via_resend(user.email, subject, message)


def send_password_reset_email(user, frontend_base_url):
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
        f"If you did not request a password reset, no action is needed.\n\n"
        f"— The Mukando Team"
    )
    _send_via_resend(user.email, subject, message)

"""
paynow_service.py — PayNow Zimbabwe Payment Gateway Integration (Mukando)

Uses the official PayNow Python SDK (pip install paynow).
SDK Docs : https://developers.paynow.co.zw/docs/python.html
Portal   : https://www.paynow.co.zw/account/integration/browse

Test Credentials (safe for local development — no real money moves):
  PAYNOW_INTEGRATION_ID  = 13
  PAYNOW_INTEGRATION_KEY = 7b60a7fc-3a7c-4187-a2e4-3c4d47de38d7

Supported Zimbabwe payment methods:
  EcoCash · OneMoney · TeleCash · ZIPIT · Visa / Mastercard
"""
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_paynow_client(return_url: str, result_url: str):
    """
    Build and return an authenticated PayNow SDK client.

    SDK constructor: Paynow(integration_id, integration_key, return_url, result_url)
    Credentials are read from Django settings so they are never hard-coded.
    In test mode the sandbox credentials defined in settings.py are used.
    """
    try:
        from paynow import Paynow  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "PayNow SDK not installed. Run: pip install paynow"
        ) from exc

    integration_id = getattr(settings, "PAYNOW_INTEGRATION_ID", "")
    integration_key = getattr(settings, "PAYNOW_INTEGRATION_KEY", "")

    if not integration_id or not integration_key:
        raise ValueError(
            "PAYNOW_INTEGRATION_ID and PAYNOW_INTEGRATION_KEY must be configured in settings."
        )

    return Paynow(
        str(integration_id),
        str(integration_key),
        return_url,   # browser redirect after payment
        result_url,   # server-side webhook from PayNow
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def initiate_payment(
    contribution,
    return_url: str,
    result_url: str,
    auth_email: Optional[str] = None,
) -> dict:
    """
    Initiate a PayNow web payment for a Mukando contribution.

    Args:
        contribution : Contribution model instance
        return_url   : Where PayNow redirects the browser after checkout
        result_url   : Where PayNow POSTs the server-side payment notification
        auth_email   : Buyer's email (falls back to contribution.user.email)

    Returns:
        On success: {"success": True, "reference": str, "redirect_url": str, "poll_url": str}
        On failure: {"success": False, "error": str}
    """
    try:
        paynow = _get_paynow_client(return_url, result_url)
    except (ImportError, ValueError, RuntimeError) as exc:
        logger.error("PayNow client init failed: %s", exc)
        return {"success": False, "error": str(exc)}

    # Build a unique reference — PayNow requires uniqueness per transaction.
    reference = f"MKD-{str(contribution.id)[:8].upper()}"

    # Auth email is required for card / online-banking methods.
    email = auth_email or getattr(contribution.user, "email", "") or ""

    # Create a Payment and attach a single line item.
    payment = paynow.create_payment(reference, email)
    description = (
        f"{contribution.group.name} contribution — {contribution.cycle_date}"
    )
    payment.add(description[:100], float(contribution.amount))

    logger.info(
        "Initiating PayNow payment | ref=%s | amount=%s",
        reference, contribution.amount,
    )

    try:
        response = paynow.send(payment)
    except Exception as exc:
        logger.error("PayNow SDK send() raised: %s", exc, exc_info=True)
        return {
            "success": False,
            "error": "Could not reach PayNow servers. Please try again later.",
        }

    if response.success:
        logger.info(
            "PayNow initiation OK | ref=%s | redirect=%s",
            reference, getattr(response, "redirect_url", "N/A"),
        )
        return {
            "success": True,
            "reference": reference,
            "redirect_url": getattr(response, "redirect_url", ""),
            "poll_url": getattr(response, "poll_url", ""),
        }

    error_msg = getattr(response, "error", "PayNow declined the request.")
    logger.error(
        "PayNow initiation FAILED | ref=%s | error=%s", reference, error_msg
    )
    return {"success": False, "error": error_msg}


def check_payment_status(poll_url: str) -> dict:
    """
    Query PayNow for the live status of a previously initiated payment.

    Args:
        poll_url: The poll_url stored on the PayNowTransaction record.

    Returns:
        {
            "paid"             : bool,
            "status"           : "paid"|"created"|"sent"|"cancelled"|"disputed"|"error",
            "amount"           : "5.00",
            "reference"        : "MKD-XXXXXXXX",
            "paynow_reference" : "<paynow internal ref>",
        }
    """
    if not poll_url:
        return {"paid": False, "status": "no_poll_url"}

    try:
        paynow = _get_paynow_client("", "")
    except (ValueError, RuntimeError, ImportError) as exc:
        return {"paid": False, "status": "error", "error": str(exc)}

    try:
        response = paynow.check_transaction_status(poll_url)
        status = str(getattr(response, "status", "unknown")).lower()
        paid = status == "paid"

        logger.info("PayNow poll | status=%s | paid=%s", status, paid)

        return {
            "paid": paid,
            "status": status,
            "amount": str(getattr(response, "amount", "0")),
            "reference": str(getattr(response, "reference", "")),
            "paynow_reference": str(getattr(response, "paynow_reference", "")),
        }
    except Exception as exc:
        logger.error("PayNow status check error: %s", exc, exc_info=True)
        return {"paid": False, "status": "error", "error": str(exc)}


def verify_result_notification(post_data: dict) -> bool:
    """
    Verify the SHA-512 hash on a PayNow server-side result notification.

    Call this inside ``paynow_result_view`` to confirm the POST came from
    PayNow and has not been tampered with.

    Returns True if hash is valid, False otherwise.
    """
    try:
        paynow = _get_paynow_client("", "")
    except (ValueError, RuntimeError, ImportError) as exc:
        logger.error("Cannot verify PayNow hash: %s", exc)
        return False

    try:
        # process_status_update verifies the hash internally and raises on mismatch.
        paynow.process_status_update(post_data)
        return True
    except Exception as exc:
        logger.warning("PayNow hash verification failed: %s", exc)
        return False


def get_payment_methods_display() -> list:
    """Return a display list of Zimbabwe payment methods accepted by PayNow."""
    return [
        {"id": "ecocash",  "name": "EcoCash",        "icon": "📱", "description": "EcoCash mobile wallet"},
        {"id": "onemoney", "name": "OneMoney",        "icon": "📱", "description": "NetOne OneMoney wallet"},
        {"id": "telecash", "name": "TeleCash",        "icon": "📱", "description": "Telecel TeleCash wallet"},
        {"id": "zipit",    "name": "ZIPIT",           "icon": "🏦", "description": "Instant bank transfer"},
        {"id": "visa",     "name": "Visa/Mastercard", "icon": "💳", "description": "Debit or credit card"},
    ]

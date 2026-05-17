"""
notification_service.py — Email + WhatsApp/SMS Notifications for Mukando
Supports:
  - Django email (SMTP / SendGrid)
  - Africa's Talking SMS/WhatsApp (widely used in Zimbabwe)
"""
import logging
from django.core.mail import EmailMultiAlternatives, send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Low-level senders ────────────────────────────────────────────────────────

def send_email_notification(user, subject: str, text_body: str, html_body: str = None) -> bool:
    """Send email to a user. Returns True on success."""
    if not user.email:
        logger.warning(f"No email for user {user.username}, skipping email notification")
        return False
    try:
        if html_body:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()
        else:
            send_mail(
                subject=subject,
                message=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        logger.info(f"Email sent to {user.email}: {subject}")
        return True
    except Exception as exc:
        logger.error(f"Email failed for {user.email}: {exc}")
        return False


def _normalize_zim_phone(phone: str) -> str:
    """Normalise a Zimbabwe phone number to E.164 format (+263...)."""
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('00263'):
        phone = '+' + phone[2:]
    elif phone.startswith('0263'):
        phone = '+263' + phone[4:]
    elif phone.startswith('07') or phone.startswith('08'):
        phone = '+263' + phone[1:]
    elif phone.startswith('263') and not phone.startswith('+'):
        phone = '+' + phone
    elif not phone.startswith('+'):
        phone = '+263' + phone
    return phone


def send_sms_whatsapp_notification(phone: str, message: str, channel: str = 'sms') -> bool:
    """
    Send SMS or WhatsApp message via Africa's Talking.
    channel: 'sms' | 'whatsapp'
    Returns True on success.
    """
    at_username = getattr(settings, 'AT_USERNAME', '')
    at_api_key = getattr(settings, 'AT_API_KEY', '')

    if not at_username or not at_api_key:
        logger.warning("Africa's Talking credentials not set — skipping SMS/WhatsApp send")
        return False

    if not phone:
        logger.warning("No phone number provided — skipping SMS/WhatsApp send")
        return False

    normalized = _normalize_zim_phone(phone)

    try:
        import africastalking
        africastalking.initialize(at_username, at_api_key)

        if channel == 'whatsapp':
            # Africa's Talking WhatsApp API (beta — requires approved template)
            # Falls back to SMS if WhatsApp not enabled on your account
            whatsapp = africastalking.Application  # placeholder; use their WhatsApp SDK when available
            # For now we use SMS as the proven channel
            sms = africastalking.SMS
            response = sms.send(message, [normalized])
        else:
            sms = africastalking.SMS
            response = sms.send(message, [normalized])

        logger.info(f"SMS/WhatsApp sent to {normalized}: {response}")
        return True
    except ImportError:
        logger.warning("africastalking package not installed — skipping SMS/WhatsApp")
        return False
    except Exception as exc:
        logger.error(f"SMS/WhatsApp failed for {normalized}: {exc}")
        return False


# ─── HTML email builder ───────────────────────────────────────────────────────

def _build_html_email(title: str, body: str, group_name: str = None, cta_text: str = None, cta_url: str = None) -> str:
    cta_html = ''
    if cta_text and cta_url:
        cta_html = f"""
        <div style="text-align:center;margin:24px 0;">
            <a href="{cta_url}" style="background:#2D6A4F;color:white;padding:12px 28px;
               border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px;">
               {cta_text}
            </a>
        </div>"""

    group_tag = f'<p style="color:#888;font-size:12px;margin-top:16px;">Group: <strong>{group_name}</strong></p>' if group_name else ''

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#2D6A4F,#40916C);padding:28px 32px;">
              <h1 style="margin:0;color:#fff;font-size:22px;">🌿 Mukando</h1>
              <p style="margin:6px 0 0;color:#b7e4c7;font-size:13px;">Community Savings Made Simple</p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="color:#2D6A4F;margin:0 0 16px;">{title}</h2>
              <div style="color:#333;font-size:15px;line-height:1.7;">{body}</div>
              {cta_html}
              {group_tag}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#f9f9f9;padding:16px 32px;border-top:1px solid #eee;">
              <p style="margin:0;color:#aaa;font-size:11px;">
                You're receiving this because you're a Mukando member. &nbsp;|&nbsp;
                <a href="#" style="color:#aaa;">Unsubscribe</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ─── High-level notification dispatcher ──────────────────────────────────────

def _dispatch_notifications(
    user, group, title, message,
    send_email, send_sms, send_whatsapp,
    cta_text, cta_url,
):
    """Send email/SMS/WhatsApp in a background thread — never blocks the request."""
    if send_email:
        try:
            html = _build_html_email(
                title=title,
                body=message.replace('\n', '<br>'),
                group_name=group.name if group else None,
                cta_text=cta_text,
                cta_url=cta_url,
            )
            send_email_notification(user, f"Mukando: {title}", message, html)
        except Exception as exc:
            logger.error("Background email failed for %s: %s", user.email, exc)

    if send_sms:
        try:
            sms_text = f"Mukando: {title}\n{message}"
            if group:
                sms_text += f"\nGroup: {group.name}"
            send_sms_whatsapp_notification(user.phone, sms_text, channel='sms')
        except Exception as exc:
            logger.error("Background SMS failed for %s: %s", user.phone, exc)

    if send_whatsapp:
        try:
            wa_text = f"🌿 *Mukando* — {title}\n{message}"
            if group:
                wa_text += f"\n📋 Group: {group.name}"
            send_sms_whatsapp_notification(user.phone, wa_text, channel='whatsapp')
        except Exception as exc:
            logger.error("Background WhatsApp failed for %s: %s", user.phone, exc)


def create_and_send_notification(
    user,
    group,
    notification_type: str,
    title: str,
    message: str,
    send_email: bool = True,
    send_sms: bool = False,
    send_whatsapp: bool = False,
    cta_text: str = None,
    cta_url: str = None,
):
    """Create a DB notification record and dispatch email/SMS/WhatsApp in background."""
    import threading
    from .models import Notification

    # Save to DB immediately — this always succeeds even if email fails
    notification = Notification.objects.create(
        user=user,
        group=group,
        notification_type=notification_type,
        title=title,
        message=message,
    )

    # Fire-and-forget: send email/SMS in background so request isn't blocked
    thread = threading.Thread(
        target=_dispatch_notifications,
        args=(user, group, title, message,
              send_email, send_sms, send_whatsapp,
              cta_text, cta_url),
        daemon=True,
    )
    thread.start()

    return notification


# ─── Specific notification helpers ───────────────────────────────────────────

def notify_payment_due(contribution, site_url: str = ''):
    """Notify user that their contribution is coming due."""
    cta_url = f"{site_url}/pay/{contribution.id}/" if site_url else None
    create_and_send_notification(
        user=contribution.user,
        group=contribution.group,
        notification_type='payment_due',
        title='Payment Due Reminder ⏰',
        message=(
            f"Hi {contribution.user.first_name or contribution.user.username},\n\n"
            f"Your contribution of {contribution.amount} {contribution.group.currency} "
            f"to <strong>{contribution.group.name}</strong> is due on "
            f"<strong>{contribution.due_date}</strong>.\n\n"
            f"Please make your payment on time to avoid being marked as late."
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
        cta_text='Pay Now with PayNow',
        cta_url=cta_url,
    )


def notify_payment_received(contribution):
    """Notify user their payment was successfully recorded."""
    create_and_send_notification(
        user=contribution.user,
        group=contribution.group,
        notification_type='payment_received',
        title='Payment Received ✅',
        message=(
            f"Great news, {contribution.user.first_name or contribution.user.username}!\n\n"
            f"Your payment of <strong>{contribution.amount} {contribution.group.currency}</strong> "
            f"for <strong>{contribution.group.name}</strong> has been successfully recorded.\n\n"
            f"Reference: {contribution.reference_number or 'N/A'}\n"
            f"Thank you for keeping up with your contributions! 💪"
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
    )


def notify_payout_scheduled(payout):
    """Notify user about their upcoming payout."""
    create_and_send_notification(
        user=payout.recipient,
        group=payout.group,
        notification_type='payout_soon',
        title='Your Payout is Coming! 🎉',
        message=(
            f"Exciting news, {payout.recipient.first_name or payout.recipient.username}!\n\n"
            f"Your payout of <strong>{payout.amount} {payout.group.currency}</strong> "
            f"from <strong>{payout.group.name}</strong> is scheduled for "
            f"<strong>{payout.payout_date}</strong>.\n\n"
            f"Make sure your payment details are up to date."
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
    )


def notify_payout_completed(payout):
    """Notify user their payout has been processed."""
    create_and_send_notification(
        user=payout.recipient,
        group=payout.group,
        notification_type='payout_done',
        title='Payout Processed Successfully! 💰',
        message=(
            f"Congratulations, {payout.recipient.first_name or payout.recipient.username}!\n\n"
            f"Your payout of <strong>{payout.amount} {payout.group.currency}</strong> "
            f"from <strong>{payout.group.name}</strong> has been processed.\n\n"
            f"Well done for staying consistent with your savings! 🌟"
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
    )


def notify_missed_payment(contribution):
    """Notify user about a missed payment."""
    create_and_send_notification(
        user=contribution.user,
        group=contribution.group,
        notification_type='missed_payment',
        title='Missed Payment Warning ⚠️',
        message=(
            f"Hi {contribution.user.first_name or contribution.user.username},\n\n"
            f"You have a missed payment of <strong>{contribution.amount} {contribution.group.currency}</strong> "
            f"to <strong>{contribution.group.name}</strong> that was due on "
            f"<strong>{contribution.due_date}</strong>.\n\n"
            f"Please make your payment as soon as possible to avoid penalties."
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
    )


def notify_group_update(group, message_text: str):
    """Notify all active group members about a general update."""
    from .models import Membership
    members = Membership.objects.filter(group=group, is_active=True).select_related('user')
    sent = 0
    for membership in members:
        create_and_send_notification(
            user=membership.user,
            group=group,
            notification_type='group_update',
            title=f'Update: {group.name}',
            message=message_text,
            send_email=True,
            send_sms=False,  # Avoid SMS spam for general updates
            send_whatsapp=False,
        )
        sent += 1
    return sent


def notify_paynow_payment_confirmed(contribution, paynow_ref: str):
    """Notify user that their PayNow payment was confirmed."""
    create_and_send_notification(
        user=contribution.user,
        group=contribution.group,
        notification_type='payment_received',
        title='PayNow Payment Confirmed ✅',
        message=(
            f"Your PayNow payment of <strong>{contribution.amount} {contribution.group.currency}</strong> "
            f"for <strong>{contribution.group.name}</strong> has been confirmed.\n\n"
            f"PayNow Reference: <strong>{paynow_ref}</strong>\n"
            f"Thank you for your timely payment!"
        ),
        send_email=True,
        send_sms=True,
        send_whatsapp=True,
    )

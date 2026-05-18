"""
rounds/utils.py — Shared utility functions for Mukando System
"""
import calendar
from datetime import date, timedelta
from .models import Payout, Membership


def _add_period(d: date, cycle_period: str) -> date:
    """Advance a date by one cycle period using only the stdlib."""
    if cycle_period == 'weekly':
        return d + timedelta(weeks=1)
    if cycle_period == 'biweekly':
        return d + timedelta(weeks=2)
    # monthly — same day next month, clamped to last day of that month
    month = d.month + 1 if d.month < 12 else 1
    year  = d.year if d.month < 12 else d.year + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_payout_schedule(group):
    """
    Create (or regenerate) Payout records for all active members in
    payout_position order, spaced by the group's cycle_period.

    - Clears all existing *pending* payouts before regenerating so the
      schedule stays in sync if members join / leave.
    - Already-paid or skipped payouts are left untouched.
    - Safe to call multiple times (idempotent for the pending state).
    """
    # Remove pending payouts so we can rebuild cleanly
    group.payouts.filter(status='pending').delete()

    members = (
        Membership.objects
        .filter(group=group, is_active=True)
        .select_related('user')
        .order_by('payout_position', 'joined_at')
    )

    if not members.exists():
        return

    # Payout amount = contribution × total number of active members
    member_count = members.count()
    payout_amount = group.contribution_amount * member_count

    # Figure out the starting round number (skip already-paid/skipped rounds)
    last_done = (
        group.payouts
        .exclude(status='pending')
        .order_by('-round_number')
        .values_list('round_number', flat=True)
        .first()
    ) or 0

    # Guard against start_date arriving as a string (e.g. straight from POST data)
    payout_date = group.start_date
    if isinstance(payout_date, str):
        from datetime import datetime
        payout_date = datetime.strptime(payout_date, '%Y-%m-%d').date()
    # Advance payout_date past already-completed rounds
    for _ in range(last_done):
        payout_date = _add_period(payout_date, group.cycle_period)

    for i, membership in enumerate(members, start=last_done + 1):
        Payout.objects.get_or_create(
            group=group,
            round_number=i,
            defaults=dict(
                recipient=membership.user,
                amount=payout_amount,
                payout_date=payout_date,
                status='pending',
            ),
        )
        payout_date = _add_period(payout_date, group.cycle_period)

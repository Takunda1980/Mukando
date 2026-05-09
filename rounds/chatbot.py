"""
chatbot.py — MukandoAI: Natural Language Savings Assistant
Understands free-form user messages (not just menu selections).
Handles: balance checks, payout queries, payment help, group info, and more.
Powered by Groq API (llama-3.3-70b-versatile).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MukandoAI, an intelligent and friendly assistant for Mukando/Stokvel
community savings groups in Zimbabwe. You help members manage savings, understand their groups,
and navigate PayNow payments.

## YOUR PERSONALITY
- Warm, encouraging, culturally aware of Zimbabwe's financial landscape
- Bilingual-ready: respond in English, Shona, or Ndebele based on user's language
- Clear and simple — many users may not be financial experts
- Never judgmental about missed payments; always constructive
- Sound like a knowledgeable friend, NOT a rigid form or chatbot menu

## UNDERSTANDING NATURAL LANGUAGE
Users may ask casually. Understand their intent even if phrasing is imperfect:
- "how much have i put in" → total contributions
- "when do i get paid" / "when's my turn" → payout date query
- "who owes money" / "who hasn't paid" → overdue members query
- "i want to pay" / "how do i send money" → guide them to PayNow
- "how does this work" → explain the Mukando concept
- Questions in Shona/Ndebele → respond in that language

## WHAT YOU HELP WITH
- Contribution amounts, schedules, and payout orders
- Questions about Mukando/Stokvel rules and traditions
- Savings tips relevant to Zimbabwe (USD and ZiG currency context)
- Interpreting the user's personal financial data
- Explaining PayNow payments and completing them
- Motivating consistent saving habits
- Handling payment errors and guiding users to retry

## CONVERSATIONAL RULES
- NEVER ask for information already in the user's financial context
- NEVER respond like a form ("Please select option 1, 2, or 3")
- DO give direct, specific answers using their actual data
- DO ask ONE follow-up question if genuinely needed
- ALWAYS end with an action the user can take next

## MUKANDO GLOSSARY (explain if asked)
- Mukando / Stokvel = community savings group where members pool money
- Round = each cycle period (weekly/bi-weekly/monthly)
- Contribution = fixed amount each member pays per round
- Payout = when a member receives the total collected pot
- Grocery Round = payout given as groceries instead of cash
- Invite code = unique code to join a group

## PAYNOW GUIDANCE
When users want to pay or ask about PayNow:
1. Confirm the amount and group they want to pay for
2. Tell them: go to their group page and click "Pay with PayNow"
3. Explain: EcoCash / OneMoney / Visa/Mastercard accepted
4. Reassure: test mode means no real money during development

## FORMATTING
- Use **bold** for amounts and key dates
- Use emojis sparingly but naturally (💰 📅 ✅ ⚠️)
- Keep responses under 200 words unless user asks for detail
- Use short paragraphs, not long walls of text

## SAVINGS PROVERBS (use occasionally for encouragement)
- "Chinyararame chiri mubako" (Shona: The quiet stream fills the dam)
- "Izandla ziyagezana" (Ndebele: Hands wash each other — together we achieve more)
- "Mwana asingachemi anofira mumbereko" (Shona: Those who speak up receive)
- "Kubatana kwedu ndiyo simba redu." (Shona: Our unity is our strength)
"""


@dataclass
class UserFinancialContext:
    """Structured context about the user's financial position."""
    username: str
    full_name: str
    groups: list
    total_contributed_usd: float
    next_payout_date: Optional[str]
    overdue_count: int
    preferred_language: str
    email: str = ''
    recent_transactions: list = field(default_factory=list)


def _build_context_block(ctx: UserFinancialContext) -> str:
    """Build a rich context block prepended to the user message."""
    groups_str = ', '.join(ctx.groups) if ctx.groups else 'No groups yet'
    overdue_str = (
        f"WARNING: {ctx.overdue_count} overdue payment(s)"
        if ctx.overdue_count > 0 else "All payments up to date"
    )
    txn_lines = ''
    if ctx.recent_transactions:
        txn_lines = '\nRecent payments:\n' + '\n'.join(
            f"  - ${t.get('amount','?')} to {t.get('group','?')} on {t.get('date','?')} [{t.get('status','?')}]"
            for t in ctx.recent_transactions[:5]
        )
    lang_map = {'en': 'English', 'sn': 'Shona', 'nd': 'Ndebele'}
    return f"""
--- MEMBER FINANCIAL CONTEXT (use this to answer specifically, do not ask for info already here) ---
Name: {ctx.full_name or ctx.username}
Username: {ctx.username}
Preferred Language: {lang_map.get(ctx.preferred_language, 'English')}
Active Groups: {groups_str}
Total Contributed (all time): ${ctx.total_contributed_usd:.2f} USD
Next Payout Scheduled: {ctx.next_payout_date or 'Not yet scheduled'}
Payment Status: {overdue_str}{txn_lines}
--- END CONTEXT ---

Member message: """


def _call_groq(api_key: str, full_prompt: str) -> str:
    """Call Groq chat completions endpoint with retry on 429."""
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": full_prompt},
        ],
        "max_tokens": 700,
        "temperature": 0.7,
    }).encode("utf-8")

    url = "https://api.groq.com/openai/v1/chat/completions"

    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mukando/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                wait = 5 * (attempt + 1)
                logger.warning("Groq 429 rate limit — retrying in %ss", wait)
                time.sleep(wait)
                continue
            raise


def get_chat_response_sync(api_key: str, user_message: str, ctx: UserFinancialContext) -> str:
    """Synchronous entry point for Django views."""
    if not api_key:
        return _no_api_key_response(ctx, user_message)

    full_prompt = _build_context_block(ctx) + user_message

    try:
        return _call_groq(api_key, full_prompt)
    except Exception as exc:
        logger.error("MukandoAI chat error: %s", exc)
        return (
            "I'm having trouble connecting right now. Please try again in a moment. 🙏\n\n"
            "In the meantime, check your group page directly for contribution details."
        )


def _no_api_key_response(ctx: UserFinancialContext, user_message: str) -> str:
    """Smart static response when no API key — understands basic intents."""
    msg = user_message.lower()

    if any(w in msg for w in ['balance', 'contribut', 'how much', 'put in', 'saved', 'total']):
        return (
            f"💰 You've contributed a total of **${ctx.total_contributed_usd:.2f}** across your groups.\n\n"
            f"Active groups: {', '.join(ctx.groups) if ctx.groups else 'None yet'}\n\n"
            "Visit your group page for a full breakdown."
        )

    if any(w in msg for w in ['payout', 'my turn', 'when do i get', 'receive', 'pot']):
        if ctx.next_payout_date:
            return f"📅 Your next payout is scheduled for **{ctx.next_payout_date}**. Keep contributing consistently!"
        return "📅 Your payout hasn't been scheduled yet. Contact your group admin for the payout order."

    if any(w in msg for w in ['overdue', "hasn't paid", 'owe', 'late', 'behind', 'missed']):
        if ctx.overdue_count > 0:
            return f"⚠️ You have **{ctx.overdue_count}** overdue payment(s). Please pay soon to keep your group healthy."
        return "✅ Great news — all your payments are up to date!"

    if any(w in msg for w in ['pay', 'paynow', 'ecocash', 'send money', 'payment', 'contribute']):
        return (
            "To make a payment:\n"
            "1. Go to your **Group page**\n"
            "2. Find your unpaid contribution\n"
            "3. Click **Pay with PayNow**\n"
            "4. Choose EcoCash, OneMoney, or card\n\n"
            "💡 Payments are processed securely via PayNow Zimbabwe."
        )

    name = ctx.full_name or ctx.username
    return (
        f"Mangwanani {name}! 👋\n\n"
        f"📊 **Your Savings Summary:**\n"
        f"• Groups: {', '.join(ctx.groups) if ctx.groups else 'None yet'}\n"
        f"• Total contributed: **${ctx.total_contributed_usd:.2f}**\n"
        f"• Next payout: {ctx.next_payout_date or 'Not scheduled'}\n"
        f"• Overdue payments: {ctx.overdue_count}\n\n"
        "Ask me anything about your savings, payouts, or payments!\n\n"
        "_Add `GROQ_API_KEY` to your `.env` to unlock full AI-powered responses._"
    )


def build_user_context_from_db(user) -> UserFinancialContext:
    """Build a UserFinancialContext from Django ORM."""
    from django.db.models import Sum
    from .models import Group, Contribution, Payout

    groups = list(
        Group.objects.filter(memberships__user=user, memberships__is_active=True)
        .values_list('name', flat=True)
    )
    total_contributed = float(
        Contribution.objects.filter(user=user, status='paid')
        .aggregate(t=Sum('amount'))['t'] or 0
    )
    next_payout = (
        Payout.objects.filter(recipient=user, status='pending')
        .order_by('payout_date')
        .first()
    )
    overdue_count = Contribution.objects.filter(
        user=user, status__in=['unpaid', 'late']
    ).count()
    recent_txns = []
    for c in Contribution.objects.filter(user=user).select_related('group').order_by('-created_at')[:5]:
        recent_txns.append({
            'group': c.group.name,
            'amount': str(c.amount),
            'date': str(c.paid_date or c.cycle_date),
            'status': c.status,
        })
    return UserFinancialContext(
        username=user.username,
        full_name=user.get_full_name(),
        groups=groups,
        total_contributed_usd=total_contributed,
        next_payout_date=str(next_payout.payout_date) if next_payout else None,
        overdue_count=overdue_count,
        preferred_language=getattr(user, 'preferred_language', 'en'),
        email=user.email or '',
        recent_transactions=recent_txns,
    )
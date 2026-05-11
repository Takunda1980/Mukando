"""
views.py — Complete Views for Mukando System
Fixes applied:
  - Username/password validation (spec-compliant)
  - N+1 fixes with select_related / prefetch_related
  - DRF rate limiting on AI chat endpoint
  - PayNow webhook note on IP allowlisting
  - WhatsApp stub clearly documented
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Sum, Count, Q, Prefetch
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework import viewsets, status, generics, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework.throttling import UserRateThrottle

import csv
import json
import re
import logging

from .models import (User, Group, Membership, Contribution, PayNowTransaction,
                     Payout, GroceryRound, GroceryItem, Notification)
from .serializers import (UserSerializer, UserRegisterSerializer, GroupSerializer,
                          MembershipSerializer, ContributionSerializer, PayoutSerializer,
                          GroceryRoundSerializer, NotificationSerializer)
from .permissions import IsGroupMember, IsGroupAdmin
from .auth_utils import send_verification_email
from .notification_service import (
    notify_payment_received, notify_payout_completed,
    notify_payout_scheduled, notify_paynow_payment_confirmed,
)
from .chatbot import get_chat_response_sync, build_user_context_from_db
from .paynow_service import (
    initiate_payment, check_payment_status,
    verify_result_notification, get_payment_methods_display,
)

logger = logging.getLogger(__name__)

# ─── Validation helpers ───────────────────────────────────────────────────────

# Username: starts with a letter, only letters/digits/underscores
USERNAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')
# Password: starts with a letter, ≥8 chars, has uppercase, lowercase, digit
PASSWORD_MIN_RE = re.compile(r'^[a-zA-Z].{7,}$')   # starts with letter, ≥8 chars


def validate_username(username: str):
    """Return error string or None."""
    if not username:
        return "Username is required."
    if not username[0].isalpha():
        return "Username must start with a letter (a–z or A–Z)."
    if not USERNAME_RE.match(username):
        return "Username may only contain letters, numbers, and underscores."
    return None


def validate_password(password: str):
    """Return error string or None."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not password[0].isalpha():
        return "Password must start with a letter."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    return None


# ─── Helper ──────────────────────────────────────────
def get_user_groups(user):
    return Group.objects.filter(memberships__user=user, memberships__is_active=True)


# ════════════════════════════════════════════════════
#  TEMPLATE VIEWS
# ════════════════════════════════════════════════════

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'rounds/home.html')


def register_view(request):
    if request.method == 'POST':
        data = request.POST

        username = data.get('username', '').strip()
        password = data.get('password', '')
        password2 = data.get('password2', '')

        # Username validation
        err = validate_username(username)
        if err:
            messages.error(request, err)
            return render(request, 'rounds/register.html')

        # Password validation
        err = validate_password(password)
        if err:
            messages.error(request, err)
            return render(request, 'rounds/register.html')

        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'rounds/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'rounds/register.html')

        if data.get('email') and User.objects.filter(email__iexact=data.get('email')).exists():
            messages.error(request, 'An account with this email already exists.')
            return render(request, 'rounds/register.html')

        # Create account as inactive — must verify email before logging in
        user = User.objects.create_user(
            username=username,
            email=data.get('email', ''),
            password=password,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            phone=data.get('phone', ''),
            preferred_language=data.get('preferred_language', 'en'),
            is_active=False,
            email_verified=False,
        )

        send_verification_email(user, request)

        messages.success(
            request,
            'Account created! Please check your email and click the '
            'verification link to activate your account before logging in.'
        )
        return redirect('login')
    return render(request, 'rounds/register.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # Check if account exists but email is unverified — give a clear message
        # rather than the generic "Invalid username or password."
        try:
            candidate = User.objects.get(username__iexact=username)
            if not candidate.is_active:
                messages.error(
                    request,
                    'Your email address has not been verified. '
                    'Please check your inbox for the verification link.'
                )
                return render(request, 'rounds/login.html')
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'rounds/login.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


def verify_email_view(request, token):
    """
    Legacy template-based email verification (old secrets.token_urlsafe tokens).
    New registrations use /api/auth/verify/<uidb64>/<token>/ instead.
    This route is kept so any old verification links that were already sent still work.
    """
    try:
        user = User.objects.get(email_verify_token=token)
        user.is_active = True
        user.email_verified = True
        user.email_verify_token = ''
        user.save(update_fields=['is_active', 'email_verified', 'email_verify_token'])
        messages.success(request, 'Email verified successfully! You can now log in.')
    except User.DoesNotExist:
        messages.error(request, 'Invalid or expired verification link.')
    return redirect('login')


@login_required
def dashboard_view(request):
    user = request.user
    groups = get_user_groups(user).prefetch_related(
        Prefetch('memberships', queryset=Membership.objects.select_related('user'))
    )

    total_contributed = Contribution.objects.filter(
        user=user, status='paid'
    ).aggregate(total=Sum('amount'))['total'] or 0

    upcoming_payouts = Payout.objects.filter(
        recipient=user, status='pending'
    ).select_related('group').order_by('payout_date')[:3]

    notifications = Notification.objects.filter(user=user, is_read=False)[:5]
    unread_count = Notification.objects.filter(user=user, is_read=False).count()

    from datetime import date, timedelta
    months = []
    for i in range(5, -1, -1):
        d = date.today().replace(day=1) - timedelta(days=i * 28)
        months.append(d.strftime('%b %Y'))

    context = {
        'groups': groups,
        'total_contributed': total_contributed,
        'upcoming_payouts': upcoming_payouts,
        'notifications': notifications,
        'unread_count': unread_count,
        'months_json': json.dumps(months),
    }
    return render(request, 'rounds/dashboard.html', context)


@login_required
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.preferred_language = request.POST.get('preferred_language', user.preferred_language)
        user.notify_email = request.POST.get('notify_email') == 'on'
        user.notify_sms = request.POST.get('notify_sms') == 'on'
        user.notify_whatsapp = request.POST.get('notify_whatsapp') == 'on'
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    return render(request, 'rounds/profile.html', {'user': user})


@login_required
def group_list_view(request):
    groups = get_user_groups(request.user)
    return render(request, 'rounds/group_list.html', {'groups': groups})


@login_required
def group_detail_view(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    membership = get_object_or_404(Membership, user=request.user, group=group, is_active=True)

    # ── N+1 fix: eager-load all related data in bulk queries ──────────────
    members = (
        Membership.objects
        .filter(group=group, is_active=True)
        .select_related('user')
        .prefetch_related(
            Prefetch(
                'user__contributions',
                queryset=Contribution.objects.filter(group=group, status='paid'),
                to_attr='group_paid_contributions',
            )
        )
    )

    contributions_qs = (
        Contribution.objects
        .filter(group=group)
        .select_related('user')
        .order_by('-cycle_date')
    )
    contributions = contributions_qs[:50]
    payouts = Payout.objects.filter(group=group).select_related('recipient')
    grocery_rounds = GroceryRound.objects.filter(group=group).select_related('recipient')

    paid_total = contributions_qs.filter(status='paid').aggregate(t=Sum('amount'))['t'] or 0

    # Replaced the slow distinct-join defaulters query with a clean subquery
    defaulter_user_ids = (
        Contribution.objects
        .filter(group=group, status__in=['unpaid', 'late'])
        .values_list('user_id', flat=True)
        .distinct()
    )
    defaulters = members.filter(user_id__in=defaulter_user_ids)

    my_unpaid = Contribution.objects.filter(
        user=request.user, group=group, status__in=['unpaid', 'late', 'partial']
    ).order_by('due_date')

    context = {
        'group': group,
        'membership': membership,
        'members': members,
        'contributions': contributions,
        'payouts': payouts,
        'grocery_rounds': grocery_rounds,
        'paid_total': paid_total,
        'defaulters': defaulters,
        'my_unpaid': my_unpaid,
        'paynow_enabled': bool(getattr(settings, 'PAYNOW_INTEGRATION_ID', '')),
    }
    return render(request, 'rounds/group_detail.html', context)


@login_required
def create_group_view(request):
    if request.method == 'POST':
        try:
            group = Group.objects.create(
                name=request.POST['name'],
                description=request.POST.get('description', ''),
                contribution_amount=request.POST['contribution_amount'],
                currency=request.POST.get('currency', 'USD'),
                cycle_period=request.POST['cycle_period'],
                start_date=request.POST['start_date'],
                max_members=request.POST.get('max_members', 20),
                allow_grocery_rounds=request.POST.get('allow_grocery_rounds') == 'on',
                created_by=request.user,
            )
            Membership.objects.create(
                user=request.user, group=group, role='admin', payout_position=1
            )
            messages.success(request, f'Group "{group.name}" created! Invite code: {group.invite_code}')
            return redirect('group_detail', group_id=group.pk)
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return render(request, 'rounds/create_group.html')


@login_required
def join_group_view(request):
    if request.method == 'POST':
        code = request.POST.get('invite_code', '').strip().upper()
        try:
            group = Group.objects.get(invite_code=code)
            if Membership.objects.filter(user=request.user, group=group).exists():
                messages.info(request, 'You are already in this group.')
            elif group.member_count() >= group.max_members:
                messages.error(request, 'Group is full.')
            else:
                pos = group.member_count() + 1
                Membership.objects.create(user=request.user, group=group, payout_position=pos)
                messages.success(request, f'Joined "{group.name}" successfully!')
                return redirect('group_detail', group_id=group.pk)
        except Group.DoesNotExist:
            messages.error(request, 'Invalid invite code.')
    return render(request, 'rounds/join_group.html')


@login_required
def contributions_view(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    get_object_or_404(Membership, user=request.user, group=group, is_active=True)
    contributions = Contribution.objects.filter(group=group).select_related('user')
    return render(request, 'rounds/contribution_list.html', {
        'group': group, 'contributions': contributions
    })


@login_required
def payout_schedule_view(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    get_object_or_404(Membership, user=request.user, group=group, is_active=True)
    payouts = Payout.objects.filter(group=group).select_related('recipient')
    return render(request, 'rounds/payout_schedule.html', {'group': group, 'payouts': payouts})


@login_required
def export_csv_view(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    get_object_or_404(Membership, user=request.user, group=group, is_active=True)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{group.name}_contributions.csv"'
    writer = csv.writer(response)
    writer.writerow(['Member', 'Amount', 'Type', 'Status', 'Cycle Date', 'Paid Date', 'Due Date', 'Reference'])
    for c in Contribution.objects.filter(group=group).select_related('user'):
        writer.writerow([
            c.user.get_full_name() or c.user.username,
            c.amount, c.contribution_type, c.status,
            c.cycle_date, c.paid_date, c.due_date, c.reference_number
        ])
    return response


@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user)
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'rounds/notifications.html', {'notifications': notifications})


@login_required
def transaction_history_view(request):
    paynow_txns = (
        PayNowTransaction.objects
        .filter(user=request.user)
        .select_related('contribution__group')
        .order_by('-initiated_at')
    )
    contributions = (
        Contribution.objects
        .filter(user=request.user)
        .select_related('group')
        .order_by('-created_at')[:50]
    )
    return render(request, 'rounds/transaction_history.html', {
        'paynow_txns': paynow_txns,
        'contributions': contributions,
    })


@login_required
def paynow_receipt_view(request, txn_id):
    txn = get_object_or_404(PayNowTransaction, pk=txn_id, user=request.user)
    return render(request, 'rounds/paynow_return.html', {
        'txn': txn,
        'success': txn.status == 'paid',
        'paynow_status': txn.status,
        'reference': txn.reference,
        'test_mode': getattr(settings, 'PAYNOW_TEST_MODE', True),
    })


@login_required
def ai_chat_view(request):
    return render(request, 'rounds/ai_chat.html')


# ════════════════════════════════════════════════════
#  PAYNOW VIEWS
# ════════════════════════════════════════════════════

@login_required
def paynow_pay_view(request, contribution_id):
    contribution = get_object_or_404(
        Contribution, pk=contribution_id, user=request.user
    )

    if contribution.status == 'paid':
        messages.info(request, 'This contribution has already been paid.')
        return redirect('group_detail', group_id=contribution.group.pk)

    payment_methods = get_payment_methods_display()
    paynow_enabled = bool(getattr(settings, 'PAYNOW_INTEGRATION_ID', ''))
    test_mode = getattr(settings, 'PAYNOW_TEST_MODE', True)

    if request.method == 'POST':
        if not paynow_enabled:
            messages.error(request, 'PayNow is not configured. Contact your administrator.')
            return redirect('group_detail', group_id=contribution.group.pk)

        return_url = request.build_absolute_uri('/paynow/return/')
        result_url = request.build_absolute_uri('/paynow/result/')

        result = initiate_payment(
            contribution=contribution,
            return_url=return_url,
            result_url=result_url,
            auth_email=request.user.email,
        )

        if result['success']:
            PayNowTransaction.objects.create(
                contribution=contribution,
                user=request.user,
                reference=result['reference'],
                poll_url=result.get('poll_url', ''),
                amount=contribution.amount,
                status='sent',
                raw_response=result,
            )
            logger.info(
                'PayNow transaction created | user=%s | ref=%s | redirect=%s',
                request.user.username, result['reference'], result.get('redirect_url'),
            )
            return redirect(result['redirect_url'])

        error_msg = result.get('error', 'PayNow is unavailable. Please try again.')
        messages.error(request, f'Payment initiation failed: {error_msg}')
        logger.warning(
            'PayNow initiation failed | user=%s | contribution=%s | error=%s',
            request.user.username, contribution_id, error_msg,
        )

    context = {
        'contribution': contribution,
        'payment_methods': payment_methods,
        'paynow_enabled': paynow_enabled,
        'test_mode': test_mode,
    }
    return render(request, 'rounds/paynow_pay.html', context)


@login_required
def paynow_return_view(request):
    status_param = request.GET.get('status', '').lower()
    reference    = request.GET.get('reference', '')

    txn = None
    if reference:
        txn = PayNowTransaction.objects.filter(
            reference=reference, user=request.user
        ).select_related('contribution__group').first()

    if txn and status_param == 'paid' and txn.status != 'paid':
        poll_result = check_payment_status(txn.poll_url)
        if poll_result.get('paid'):
            txn.mark_paid(poll_result.get('paynow_reference', ''))
            notify_paynow_payment_confirmed(txn.contribution, poll_result.get('paynow_reference', ''))

    is_paid = txn.status == 'paid' if txn else False

    context = {
        'paynow_status': status_param,
        'reference': reference,
        'txn': txn,
        'success': is_paid,
        'test_mode': getattr(settings, 'PAYNOW_TEST_MODE', True),
    }
    return render(request, 'rounds/paynow_return.html', context)


@csrf_exempt
# NOTE: This endpoint is intentionally csrf_exempt because PayNow POSTs from
# their servers, not from a browser. All requests are verified via SHA-512
# hash (verify_result_notification). For additional hardening in production,
# consider IP-allowlisting PayNow's server ranges at the reverse-proxy level.
def paynow_result_view(request):
    if request.method != 'POST':
        return HttpResponse('OK')

    flat_data = {
        k: (v[0] if isinstance(v, list) else v)
        for k, v in request.POST.items()
    }

    logger.info('PayNow result webhook received | data=%s', flat_data)

    if not verify_result_notification(flat_data):
        logger.warning('PayNow result webhook: hash mismatch | data=%s', flat_data)
        return HttpResponse('HASH_MISMATCH', status=400)

    reference     = flat_data.get('reference', '')
    paynow_status = flat_data.get('status', '').lower()
    paynow_ref    = flat_data.get('paynowreference', '')

    try:
        txn = PayNowTransaction.objects.select_related('contribution').get(
            reference=reference
        )
        txn.raw_response = flat_data
        txn.save(update_fields=['raw_response'])

        if paynow_status == 'paid' and txn.status != 'paid':
            txn.mark_paid(paynow_ref)
            notify_paynow_payment_confirmed(txn.contribution, paynow_ref)
            logger.info(
                'PayNow payment confirmed | ref=%s | paynow_ref=%s',
                reference, paynow_ref,
            )
        elif paynow_status in ('cancelled', 'failed', 'disputed'):
            # Map each terminal state properly
            txn.status = paynow_status if paynow_status in ('cancelled', 'failed') else 'failed'
            txn.save(update_fields=['status'])
            logger.info('PayNow payment %s | ref=%s', paynow_status, reference)

    except PayNowTransaction.DoesNotExist:
        logger.error(
            'PayNow result webhook: unknown reference=%s | data=%s',
            reference, flat_data,
        )

    return HttpResponse('OK')


@login_required
def paynow_status_view(request, contribution_id):
    contribution = get_object_or_404(
        Contribution, pk=contribution_id, user=request.user
    )
    txn = (
        PayNowTransaction.objects
        .filter(contribution=contribution)
        .order_by('-initiated_at')
        .first()
    )

    if not txn:
        return JsonResponse({'paid': False, 'status': 'no_transaction'})

    if txn.status == 'paid':
        return JsonResponse({'paid': True, 'status': 'paid', 'reference': txn.reference})

    if not txn.poll_url:
        return JsonResponse({'paid': False, 'status': txn.status})

    result = check_payment_status(txn.poll_url)

    if result.get('paid') and txn.status != 'paid':
        txn.mark_paid(result.get('paynow_reference', ''))
        notify_paynow_payment_confirmed(contribution, result.get('paynow_reference', ''))

    return JsonResponse(result)


# ════════════════════════════════════════════════════
#  REST API VIEWSETS
# ════════════════════════════════════════════════════

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(pk=self.request.user.pk)

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user).data)


# api_register and api_login have been replaced by the JWT auth views in auth_views.py.
# See: POST /api/auth/register/  and  POST /api/auth/login/


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Group.objects.filter(
            memberships__user=self.request.user, memberships__is_active=True
        ).distinct()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        group = self.get_object()
        if Membership.objects.filter(user=request.user, group=group).exists():
            return Response({'error': 'Already a member'}, status=400)
        if group.member_count() >= group.max_members:
            return Response({'error': 'Group is full'}, status=400)
        pos = group.member_count() + 1
        m = Membership.objects.create(user=request.user, group=group, payout_position=pos)
        return Response(MembershipSerializer(m).data, status=201)

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        group = self.get_object()
        data = {
            'total_collected': float(group.total_collected()),
            'member_count': group.member_count(),
            'defaulters': Contribution.objects.filter(
                group=group, status__in=['late', 'unpaid']
            ).values('user__username').distinct().count(),
            'next_payout': PayoutSerializer(
                group.payouts.filter(status='pending').order_by('payout_date').first()
            ).data if group.payouts.filter(status='pending').exists() else None,
        }
        return Response(data)


class ContributionViewSet(viewsets.ModelViewSet):
    serializer_class = ContributionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_groups = get_user_groups(self.request.user)
        qs = Contribution.objects.filter(group__in=user_groups)
        if gid := self.request.query_params.get('group'):
            qs = qs.filter(group_id=gid)
        if uid := self.request.query_params.get('user'):
            qs = qs.filter(user_id=uid)
        return qs.select_related('user', 'group')

    def perform_create(self, serializer):
        user_id = serializer.validated_data.pop('user_id')
        user = User.objects.get(pk=user_id)
        contribution = serializer.save(user=user, recorded_by=self.request.user)
        if contribution.status == 'paid':
            notify_payment_received(contribution)

    def perform_update(self, serializer):
        old_status = self.get_object().status
        contribution = serializer.save()
        if old_status != 'paid' and contribution.status == 'paid':
            notify_payment_received(contribution)


class PayoutViewSet(viewsets.ModelViewSet):
    serializer_class = PayoutSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_groups = get_user_groups(self.request.user)
        return Payout.objects.filter(group__in=user_groups).select_related('recipient', 'group')

    def perform_create(self, serializer):
        recipient_id = serializer.validated_data.pop('recipient_id')
        recipient = User.objects.get(pk=recipient_id)
        payout = serializer.save(recipient=recipient)
        notify_payout_scheduled(payout)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        payout = self.get_object()
        payout.status = 'paid'
        payout.actual_payout_date = timezone.now().date()
        payout.approved_by = request.user
        payout.save()
        notify_payout_completed(payout)
        return Response({'status': 'paid'})


class GroceryRoundViewSet(viewsets.ModelViewSet):
    serializer_class = GroceryRoundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_groups = get_user_groups(self.request.user)
        return GroceryRound.objects.filter(group__in=user_groups).select_related('recipient', 'group')


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'done'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({'status': 'done'})


# ─── Throttle: 20 AI requests per user per day ───────────────────────────────
class AIChatThrottle(UserRateThrottle):
    rate = '20/day'


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ai_chat_api(request):
    # Manual throttle check (works with @api_view decorator)
    throttle = AIChatThrottle()
    if not throttle.allow_request(request, None):
        return Response(
            {'error': 'Rate limit reached. You can send up to 20 messages per day.'},
            status=429
        )

    message = request.data.get('message', '').strip()
    if not message:
        return Response({'error': 'Empty message'}, status=400)

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    ctx = build_user_context_from_db(request.user)

    reply = get_chat_response_sync(api_key, message, ctx)
    return Response({'response': reply})


# ─── PayNow API endpoint ──────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_paynow_initiate(request):
    contribution_id = request.data.get('contribution_id')
    if not contribution_id:
        return Response({'error': 'contribution_id required'}, status=400)

    contribution = get_object_or_404(Contribution, pk=contribution_id, user=request.user)

    return_url = request.data.get('return_url', request.build_absolute_uri('/paynow/return/'))
    result_url = request.data.get('result_url', request.build_absolute_uri('/paynow/result/'))

    result = initiate_payment(
        contribution=contribution,
        return_url=return_url,
        result_url=result_url,
        auth_email=request.user.email,
    )

    if result['success']:
        PayNowTransaction.objects.create(
            contribution=contribution,
            user=request.user,
            reference=result['reference'],
            poll_url=result.get('poll_url', ''),
            amount=contribution.amount,
            status='sent',
            raw_response=result,
        )
        return Response(result, status=201)
    return Response({'error': result.get('error')}, status=502)

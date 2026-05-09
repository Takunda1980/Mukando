"""
Mukando / Stokvel Management System — Django Models
Python 3.8+ compatible
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import MinValueValidator
import uuid
import secrets


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    email_verify_token = models.CharField(max_length=64, blank=True)
    preferred_language = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('sn', 'Shona'), ('nd', 'Ndebele')],
        default='en',
    )
    national_id = models.CharField(max_length=30, blank=True)
    notify_email = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    notify_whatsapp = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.email})"

    def generate_verify_token(self):
        token = secrets.token_urlsafe(32)
        self.email_verify_token = token
        self.save(update_fields=['email_verify_token'])
        return token


class Group(models.Model):
    CYCLE_CHOICES = [('weekly','Weekly'),('biweekly','Bi-Weekly'),('monthly','Monthly')]
    STATUS_CHOICES = [('active','Active'),('paused','Paused'),('completed','Completed')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    contribution_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=5, default='USD')
    cycle_period = models.CharField(max_length=20, choices=CYCLE_CHOICES, default='monthly')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    invite_code = models.CharField(max_length=12, unique=True, blank=True)
    max_members = models.PositiveIntegerField(default=20)
    allow_grocery_rounds = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'groups'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.cycle_period})"

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(8)[:12].upper()
        super().save(*args, **kwargs)

    def total_collected(self):
        return self.contributions.filter(status='paid').aggregate(
            total=models.Sum('amount'))['total'] or 0

    def member_count(self):
        return self.memberships.filter(is_active=True).count()


class Membership(models.Model):
    ROLE_CHOICES = [('admin','Admin'),('treasurer','Treasurer'),('member','Member')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    payout_position = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'memberships'
        unique_together = ('user', 'group')
        ordering = ['payout_position', 'joined_at']

    def __str__(self):
        return f"{self.user.username} in {self.group.name} [{self.role}]"

    def total_contributed(self):
        return self.user.contributions.filter(
            group=self.group, status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0


class Contribution(models.Model):
    TYPE_CHOICES = [
        ('cash','Cash'),('grocery','Grocery'),
        ('mobile_money','Mobile Money'),('bank','Bank Transfer'),
        ('paynow','PayNow Online'),
    ]
    STATUS_CHOICES = [
        ('paid','Paid'),('unpaid','Unpaid'),
        ('late','Late'),('partial','Partial'),('waived','Waived'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contributions')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='contributions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    contribution_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='cash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    cycle_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    due_date = models.DateField()
    reference_number = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_contributions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contributions'
        ordering = ['-cycle_date']
        indexes = [
            models.Index(fields=['group', 'status'], name='contrib_group_status_idx'),
            models.Index(fields=['user', 'status'], name='contrib_user_status_idx'),
            models.Index(fields=['status', 'due_date'], name='contrib_status_due_idx'),
            models.Index(fields=['cycle_date'], name='contrib_cycle_date_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.amount} ({self.status})"

    @property
    def is_overdue(self):
        return self.status in ('unpaid','partial') and timezone.now().date() > self.due_date


class PayNowTransaction(models.Model):
    STATUS_CHOICES = [
        ('initiated','Initiated'),('sent','Sent'),
        ('paid','Paid'),('cancelled','Cancelled'),
        ('disputed','Disputed'),('failed','Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contribution = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='paynow_transactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='paynow_transactions')
    reference = models.CharField(max_length=60, unique=True)
    paynow_reference = models.CharField(max_length=120, blank=True)
    poll_url = models.URLField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')
    initiated_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'paynow_transactions'
        ordering = ['-initiated_at']

    def __str__(self):
        return f"PayNow {self.reference} — {self.status}"

    def mark_paid(self, paynow_ref: str):
        self.status = 'paid'
        self.paynow_reference = paynow_ref
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'paynow_reference', 'confirmed_at'])
        self.contribution.status = 'paid'
        self.contribution.paid_date = timezone.now().date()
        self.contribution.contribution_type = 'paynow'
        self.contribution.reference_number = paynow_ref
        self.contribution.save(update_fields=['status', 'paid_date', 'contribution_type', 'reference_number'])


class Payout(models.Model):
    STATUS_CHOICES = [('pending','Pending'),('paid','Paid'),('skipped','Skipped')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='payouts')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    round_number = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_date = models.DateField()
    actual_payout_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_payouts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payouts'
        ordering = ['round_number']
        unique_together = ('group', 'round_number')

    def __str__(self):
        return f"Round {self.round_number} → {self.recipient.username}"


class GroceryRound(models.Model):
    STATUS_CHOICES = [('planned','Planned'),('delivered','Delivered'),('cancelled','Cancelled')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='grocery_rounds')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grocery_rounds')
    round_number = models.PositiveIntegerField()
    total_value = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_date = models.DateField()
    actual_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'grocery_rounds'
        ordering = ['round_number']

    def __str__(self):
        return f"Grocery Round {self.round_number} → {self.recipient.username}"


class GroceryItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grocery_round = models.ForeignKey(GroceryRound, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=120)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    unit = models.CharField(max_length=20, default='unit')
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        db_table = 'grocery_items'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class Notification(models.Model):
    TYPE_CHOICES = [
        ('payment_due','Payment Due'),('payment_received','Payment Received'),
        ('payout_soon','Payout Coming'),('payout_done','Payout Done'),
        ('missed_payment','Missed Payment'),('group_update','Group Update'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.user.username}"

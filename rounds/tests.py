"""
tests.py — Core test suite for Mukando
Covers: credential validation, mark_paid(), PayNow webhook hash, contribution transitions.
Run: python manage.py test rounds
"""
import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Group, Membership, Contribution, PayNowTransaction, Payout, Notification
from .views import validate_username, validate_password

User = get_user_model()


# ── Validation helpers ────────────────────────────────────────────────────────

class UsernameValidationTests(TestCase):

    def test_valid_username(self):
        self.assertIsNone(validate_username('takunda_m'))
        self.assertIsNone(validate_username('Alice123'))
        self.assertIsNone(validate_username('z'))

    def test_username_must_start_with_letter(self):
        self.assertIsNotNone(validate_username('1takunda'))
        self.assertIsNotNone(validate_username('123'))
        self.assertIsNotNone(validate_username('_hidden'))

    def test_username_invalid_chars(self):
        self.assertIsNotNone(validate_username('take@world'))
        self.assertIsNotNone(validate_username('john doe'))
        self.assertIsNotNone(validate_username('john-doe'))

    def test_empty_username(self):
        self.assertIsNotNone(validate_username(''))
        self.assertIsNotNone(validate_username(None))


class PasswordValidationTests(TestCase):

    def test_valid_password(self):
        self.assertIsNone(validate_password('Mukando1'))
        self.assertIsNone(validate_password('Harare2024!'))

    def test_too_short(self):
        self.assertIsNotNone(validate_password('Ab1'))
        self.assertIsNotNone(validate_password('Short1'))

    def test_must_start_with_letter(self):
        self.assertIsNotNone(validate_password('1Abcdefg'))

    def test_missing_uppercase(self):
        self.assertIsNotNone(validate_password('alllower1'))

    def test_missing_lowercase(self):
        self.assertIsNotNone(validate_password('ALLUPPER1'))

    def test_missing_digit(self):
        self.assertIsNotNone(validate_password('NoNumbers!'))

    def test_exactly_8_chars_all_rules_met(self):
        self.assertIsNone(validate_password('Abc1defg'))


# ── Model: mark_paid ─────────────────────────────────────────────────────────

class MarkPaidTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='Test1234')
        self.group = Group.objects.create(
            name='Test Group', contribution_amount=Decimal('50.00'),
            cycle_period='monthly', start_date=date.today(),
        )
        self.contribution = Contribution.objects.create(
            user=self.user, group=self.group,
            amount=Decimal('50.00'), status='unpaid',
            cycle_date=date.today(), due_date=date.today(),
        )
        self.txn = PayNowTransaction.objects.create(
            contribution=self.contribution,
            user=self.user,
            reference='MKD-TEST01',
            amount=Decimal('50.00'),
            status='sent',
        )

    def test_mark_paid_updates_transaction(self):
        self.txn.mark_paid('PN-CONF-999')
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, 'paid')
        self.assertEqual(self.txn.paynow_reference, 'PN-CONF-999')
        self.assertIsNotNone(self.txn.confirmed_at)

    def test_mark_paid_updates_contribution(self):
        self.txn.mark_paid('PN-CONF-999')
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.status, 'paid')
        self.assertEqual(self.contribution.paid_date, timezone.now().date())
        self.assertEqual(self.contribution.contribution_type, 'paynow')
        self.assertEqual(self.contribution.reference_number, 'PN-CONF-999')

    def test_mark_paid_idempotent(self):
        """Calling mark_paid twice should not raise and keeps status paid."""
        self.txn.mark_paid('PN-CONF-001')
        self.txn.mark_paid('PN-CONF-002')
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, 'paid')


# ── PayNow webhook hash verification ─────────────────────────────────────────

class PayNowWebhookVerificationTests(TestCase):

    def test_valid_hash_accepted(self):
        from .paynow_service import verify_result_notification
        mock_paynow = MagicMock()
        mock_paynow.process_status_update.return_value = None
        with patch('rounds.paynow_service._get_paynow_client', return_value=mock_paynow):
            result = verify_result_notification({'status': 'paid', 'hash': 'abc'})
        self.assertTrue(result)

    def test_tampered_hash_rejected(self):
        from .paynow_service import verify_result_notification
        mock_paynow = MagicMock()
        mock_paynow.process_status_update.side_effect = Exception("Hash mismatch")
        with patch('rounds.paynow_service._get_paynow_client', return_value=mock_paynow):
            result = verify_result_notification({'status': 'paid', 'hash': 'WRONG'})
        self.assertFalse(result)

    def test_missing_paynow_config_returns_false(self):
        from .paynow_service import verify_result_notification
        with patch('rounds.paynow_service._get_paynow_client',
                   side_effect=ValueError("Not configured")):
            result = verify_result_notification({'status': 'paid'})
        self.assertFalse(result)


# ── Contribution status transitions ──────────────────────────────────────────

class ContributionStatusTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='member1', password='Test1234')
        self.group = Group.objects.create(
            name='MyGroup', contribution_amount=Decimal('30.00'),
            cycle_period='monthly', start_date=date.today(),
        )

    def test_is_overdue_unpaid_past_due(self):
        c = Contribution.objects.create(
            user=self.user, group=self.group,
            amount=Decimal('30.00'), status='unpaid',
            cycle_date=date(2020, 1, 1), due_date=date(2020, 1, 31),
        )
        self.assertTrue(c.is_overdue)

    def test_is_overdue_paid_not_overdue(self):
        c = Contribution.objects.create(
            user=self.user, group=self.group,
            amount=Decimal('30.00'), status='paid',
            cycle_date=date(2020, 1, 1), due_date=date(2020, 1, 31),
        )
        self.assertFalse(c.is_overdue)

    def test_is_overdue_future_due_date(self):
        c = Contribution.objects.create(
            user=self.user, group=self.group,
            amount=Decimal('30.00'), status='unpaid',
            cycle_date=date.today(), due_date=date(2099, 12, 31),
        )
        self.assertFalse(c.is_overdue)

    def test_group_total_collected_only_counts_paid(self):
        Contribution.objects.create(
            user=self.user, group=self.group, amount=Decimal('30.00'),
            status='paid', cycle_date=date.today(), due_date=date.today(),
        )
        Contribution.objects.create(
            user=self.user, group=self.group, amount=Decimal('30.00'),
            status='unpaid', cycle_date=date.today(), due_date=date.today(),
        )
        self.assertEqual(self.group.total_collected(), Decimal('30.00'))

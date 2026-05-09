"""
Management command: python manage.py seed_demo_data
Creates demo users, groups, contributions, and payouts for testing.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random

from rounds.models import (
    UserProfile, Group, GroupMembership, Contribution, Payout,
    GroceryRound, GroceryItem, Notification
)


class Command(BaseCommand):
    help = 'Seed the database with demo Mukando data for testing'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding demo data...')

        # ── Create demo users ─────────────────────────────────────
        users_data = [
            ('admin',    'Tendai',   'Moyo',    'admin@mukando.zw',    'admin123',    True),
            ('takudzwa', 'Takudzwa', 'Nhira',   'tk@mukando.zw',       'mukando123',  False),
            ('sisi',     'Sisi',     'Dube',    'sisi@mukando.zw',     'mukando123',  False),
            ('john',     'John',     'Banda',   'john@mukando.zw',     'mukando123',  False),
            ('grace',    'Grace',    'Mutasa',  'grace@mukando.zw',    'mukando123',  False),
            ('peter',    'Peter',    'Ncube',   'peter@mukando.zw',    'mukando123',  False),
        ]

        created_users = []
        for username, first, last, email, pwd, is_staff in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': first,
                    'last_name': last,
                    'is_staff': is_staff,
                    'is_superuser': is_staff,
                }
            )
            if created:
                user.set_password(pwd)
                user.save()
                self.stdout.write(f'  ✓ Created user: {username}')
            UserProfile.objects.get_or_create(user=user, defaults={'phone_number': '+263 77 000 0001'})
            created_users.append(user)

        admin_user = created_users[0]

        # ── Create Group 1: Monthly cash group ───────────────────
        group1, _ = Group.objects.get_or_create(
            name='Harare Ladies Mukando',
            defaults={
                'description': 'A monthly savings group for Harare ladies. $100 per member per month.',
                'contribution_amount': Decimal('100.00'),
                'cycle_period': 'monthly',
                'start_date': date.today() - timedelta(days=90),
                'created_by': admin_user,
                'current_round': 3,
                'invite_code': 'LADIES01',
            }
        )
        self.stdout.write(f'  ✓ Group 1: {group1.name}')

        group1_members = created_users[:5]  # first 5 users
        for i, user in enumerate(group1_members):
            role = 'admin' if user == admin_user else ('treasurer' if i == 1 else 'member')
            GroupMembership.objects.get_or_create(
                user=user, group=group1,
                defaults={'role': role, 'payout_order': i + 1, 'is_active': True}
            )

        group1.total_rounds = len(group1_members)
        group1.save()

        # Payouts for group 1
        Payout.objects.filter(group=group1).delete()
        payout_amt = group1.contribution_amount * len(group1_members)
        for i, user in enumerate(group1_members):
            payout_date = group1.start_date + timedelta(days=30 * i)
            status = 'paid' if i < 2 else 'pending'
            Payout.objects.create(
                group=group1,
                recipient=user,
                round_number=i + 1,
                amount=payout_amt,
                scheduled_date=payout_date,
                paid_date=payout_date if status == 'paid' else None,
                status=status
            )

        # Contributions for group 1
        Contribution.objects.filter(group=group1).delete()
        for round_num in range(1, 4):
            for j, user in enumerate(group1_members):
                contrib_date = group1.start_date + timedelta(days=30 * (round_num - 1))
                paid = paid_date = None
                if round_num <= 2:
                    status = 'paid'
                    paid_date = contrib_date + timedelta(days=random.randint(0, 3))
                elif round_num == 3:
                    status = random.choice(['paid', 'paid', 'unpaid', 'late'])
                    paid_date = contrib_date if status == 'paid' else None
                else:
                    status = 'unpaid'
                    paid_date = None

                Contribution.objects.create(
                    group=group1,
                    member=user,
                    round_number=round_num,
                    amount=group1.contribution_amount,
                    contribution_type='cash',
                    status=status,
                    due_date=contrib_date,
                    paid_date=paid_date,
                    recorded_by=admin_user
                )

        # ── Create Group 2: Weekly grocery group ─────────────────
        group2, _ = Group.objects.get_or_create(
            name='Mbare Grocery Circle',
            defaults={
                'description': 'Weekly grocery round for Mbare community members.',
                'contribution_amount': Decimal('30.00'),
                'cycle_period': 'weekly',
                'start_date': date.today() - timedelta(weeks=8),
                'created_by': created_users[1],
                'current_round': 3,
                'invite_code': 'MBARE001',
            }
        )
        self.stdout.write(f'  ✓ Group 2: {group2.name}')

        group2_members = created_users[1:]  # last 5 users
        for i, user in enumerate(group2_members):
            role = 'admin' if i == 0 else ('treasurer' if i == 1 else 'member')
            GroupMembership.objects.get_or_create(
                user=user, group=group2,
                defaults={'role': role, 'payout_order': i + 1, 'is_active': True}
            )

        group2.total_rounds = len(group2_members)
        group2.save()

        # Grocery rounds for group 2
        GroceryRound.objects.filter(group=group2).delete()
        grocery_beneficiaries = group2_members[:3]
        grocery_items_data = [
            [('Maize Meal 10kg', '1 bag', 18.00), ('Cooking Oil 2L', '1 bottle', 6.00), ('Sugar 2kg', '1 bag', 4.00)],
            [('Rice 5kg', '1 bag', 12.00), ('Beans 2kg', '1 bag', 8.00), ('Tomatoes', '1 kg', 3.00), ('Onions', '500g', 2.00)],
            [('Bread Flour 10kg', '1 bag', 14.00), ('Eggs', '1 tray (30)', 9.00), ('Milk 2L', '2 bottles', 5.00)],
        ]

        for i, user in enumerate(grocery_beneficiaries):
            gr = GroceryRound.objects.create(
                group=group2,
                beneficiary=user,
                round_number=i + 1,
                scheduled_date=group2.start_date + timedelta(weeks=i),
                status='delivered' if i < 2 else 'collected',
                total_value=sum(v for _, _, v in grocery_items_data[i]),
                notes='Delivered successfully' if i < 2 else 'Ready for pickup'
            )
            for name, qty, val in grocery_items_data[i]:
                GroceryItem.objects.create(
                    grocery_round=gr,
                    contributed_by=group2_members[(i + 1) % len(group2_members)],
                    item_name=name,
                    quantity=qty,
                    estimated_value=Decimal(str(val))
                )

        # ── Notifications ─────────────────────────────────────────
        for user in created_users:
            Notification.objects.get_or_create(
                user=user,
                title='Welcome to Mukando! 🎉',
                defaults={
                    'message': 'Your account is set up. You have been added to demo groups.',
                    'notification_type': 'welcome',
                }
            )

        Notification.objects.get_or_create(
            user=admin_user,
            title='Payout Due: Harare Ladies Mukando',
            defaults={
                'message': f'Round 3 payout of ${payout_amt} is due to {group1_members[2].get_full_name()} this month.',
                'notification_type': 'payout',
                'group': group1,
            }
        )

        self.stdout.write(self.style.SUCCESS(
            '\n✅ Demo data seeded successfully!\n'
            '\n🔑 Login credentials:'
            '\n   Admin:      admin / admin123'
            '\n   Member:     takudzwa / mukando123'
            '\n   Member:     sisi / mukando123'
            '\n   Member:     john / mukando123'
            '\n\n🌐 Run: python manage.py runserver'
            '\n📍 Visit: http://127.0.0.1:8000/'
        ))

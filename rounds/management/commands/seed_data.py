"""
Management command: python manage.py seed_data
Creates sample groups, members, contributions for testing.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import random

class Command(BaseCommand):
    help = 'Seed database with sample Mukando data'

    def handle(self, *args, **options):
        from rounds.models import User, Group, Membership, Contribution, Payout, GroceryRound

        self.stdout.write('Creating sample data...')

        # Users
        users_data = [
            ('tendai_moyo', 'Tendai', 'Moyo', 'tendai@example.com', '+263771234567'),
            ('sisi_ncube', 'Sisi', 'Ncube', 'sisi@example.com', '+263772345678'),
            ('tatenda_choto', 'Tatenda', 'Choto', 'tatenda@example.com', '+263773456789'),
            ('rudo_dube', 'Rudo', 'Dube', 'rudo@example.com', '+263774567890'),
            ('farai_banda', 'Farai', 'Banda', 'farai@example.com', '+263775678901'),
        ]
        users = []
        for uname, fn, ln, email, phone in users_data:
            u, created = User.objects.get_or_create(username=uname, defaults={
                'first_name':fn,'last_name':ln,'email':email,'phone':phone,'email_verified':True
            })
            if created:
                u.set_password('mukando123')
                u.save()
            users.append(u)
            self.stdout.write(f'  User: {fn} {ln}')

        # Group 1: Cash Mukando
        g1, _ = Group.objects.get_or_create(
            name='Mbare Ladies Mukando',
            defaults={
                'description':'Monthly cash rotation for Mbare community ladies.',
                'contribution_amount': 50,
                'currency':'USD',
                'cycle_period':'monthly',
                'start_date': date.today() - timedelta(days=120),
                'max_members':10,
                'allow_grocery_rounds':True,
                'created_by': users[0],
            }
        )

        # Memberships
        for i, user in enumerate(users):
            Membership.objects.get_or_create(user=user, group=g1, defaults={
                'role':'admin' if i==0 else 'member',
                'payout_position': i+1,
            })

        # Contributions (last 3 months)
        statuses = ['paid','paid','paid','late','unpaid']
        for user in users:
            for month_offset in range(3):
                cycle = date.today().replace(day=1) - timedelta(days=month_offset*30)
                due = cycle + timedelta(days=7)
                paid_date = cycle + timedelta(days=random.randint(0,10)) if random.random()>0.2 else None
                st = 'paid' if paid_date else 'unpaid'
                Contribution.objects.get_or_create(
                    user=user, group=g1, cycle_date=cycle,
                    defaults={
                        'amount':50,'contribution_type':'cash',
                        'status':st,'due_date':due,'paid_date':paid_date,
                    }
                )

        # Payouts
        for i, user in enumerate(users[:3]):
            pdate = g1.start_date + timedelta(days=(i+1)*30)
            Payout.objects.get_or_create(
                group=g1, round_number=i+1,
                defaults={
                    'recipient':user,'amount':250,
                    'payout_date':pdate,
                    'status':'paid' if i<2 else 'pending',
                    'actual_payout_date':pdate if i<2 else None,
                }
            )

        # Grocery Round
        if g1.allow_grocery_rounds:
            gr, _ = GroceryRound.objects.get_or_create(
                group=g1, round_number=1,
                defaults={
                    'recipient':users[0],'total_value':80,
                    'delivery_date':date.today()-timedelta(days=30),
                    'status':'delivered',
                }
            )

        self.stdout.write(self.style.SUCCESS(f'\n✅ Sample data created!'))
        self.stdout.write(f'Group invite code: {g1.invite_code}')
        self.stdout.write(f'Login: tendai_moyo / mukando123')

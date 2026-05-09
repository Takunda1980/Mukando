from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Group, Membership, Contribution, PayNowTransaction, Payout, GroceryRound, GroceryItem, Notification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'phone', 'email_verified', 'preferred_language', 'created_at']
    list_filter = ['email_verified', 'preferred_language', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Mukando Profile', {'fields': ('phone', 'avatar', 'national_id', 'preferred_language',
                                        'email_verified', 'notify_email', 'notify_sms', 'notify_whatsapp')}),
    )


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'currency', 'cycle_period', 'status', 'member_count', 'total_collected', 'created_at']
    list_filter = ['status', 'cycle_period', 'currency']
    search_fields = ['name', 'invite_code']
    readonly_fields = ['invite_code', 'created_at', 'updated_at']


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'role', 'payout_position', 'is_active', 'joined_at']
    list_filter = ['role', 'is_active']
    search_fields = ['user__username', 'group__name']


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'amount', 'contribution_type', 'status', 'cycle_date', 'due_date']
    list_filter = ['status', 'contribution_type']
    search_fields = ['user__username', 'group__name', 'reference_number']
    date_hierarchy = 'cycle_date'


@admin.register(PayNowTransaction)
class PayNowTransactionAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'amount', 'status', 'initiated_at', 'confirmed_at']
    list_filter = ['status']
    search_fields = ['reference', 'paynow_reference', 'user__username']
    readonly_fields = ['initiated_at', 'raw_response']


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['group', 'recipient', 'round_number', 'amount', 'payout_date', 'status']
    list_filter = ['status']
    search_fields = ['recipient__username', 'group__name']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['user__username', 'title']


admin.site.register(GroceryRound)
admin.site.register(GroceryItem)

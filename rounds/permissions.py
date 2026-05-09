"""
rounds/permissions.py — Custom DRF Permissions for Mukando System
"""
from rest_framework.permissions import BasePermission
from .models import Membership


class IsGroupMember(BasePermission):
    """Allow access only to active members of the group."""
    message = 'You must be an active member of this group.'

    def has_object_permission(self, request, view, obj):
        # obj can be a Group, Contribution, Payout, or GroceryRound
        group = getattr(obj, 'group', obj)
        return Membership.objects.filter(
            user=request.user,
            group=group,
            is_active=True
        ).exists()


class IsGroupAdmin(BasePermission):
    """Allow access only to group admins or treasurers."""
    message = 'You must be a group admin or treasurer to perform this action.'

    def has_object_permission(self, request, view, obj):
        group = getattr(obj, 'group', obj)
        return Membership.objects.filter(
            user=request.user,
            group=group,
            role__in=['admin', 'treasurer'],
            is_active=True
        ).exists()


class IsGroupAdminOrReadOnly(BasePermission):
    """Read-only for all group members; write access for admins/treasurers only."""
    def has_object_permission(self, request, view, obj):
        from rest_framework.permissions import SAFE_METHODS
        if request.method in SAFE_METHODS:
            group = getattr(obj, 'group', obj)
            return Membership.objects.filter(
                user=request.user, group=group, is_active=True
            ).exists()
        # Write
        group = getattr(obj, 'group', obj)
        return Membership.objects.filter(
            user=request.user, group=group,
            role__in=['admin', 'treasurer'], is_active=True
        ).exists()

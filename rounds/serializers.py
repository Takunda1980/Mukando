"""
serializers.py — DRF Serializers for Mukando System
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Group, Membership, Contribution, Payout, GroceryRound, GroceryItem, Notification

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'phone', 'preferred_language', 'email_verified', 'created_at']
        read_only_fields = ['id', 'email_verified', 'created_at']


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name',
                  'phone', 'password', 'password2', 'preferred_language']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    total_contributed = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'payout_position', 'is_active',
                  'joined_at', 'total_contributed', 'notes']

    def get_total_contributed(self, obj):
        return float(obj.total_contributed())


class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    total_collected = serializers.SerializerMethodField()
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'contribution_amount', 'currency',
                  'cycle_period', 'start_date', 'end_date', 'status', 'invite_code',
                  'max_members', 'allow_grocery_rounds', 'created_by',
                  'member_count', 'total_collected', 'created_at']
        read_only_fields = ['id', 'invite_code', 'created_by', 'created_at']

    def get_member_count(self, obj):
        return obj.member_count()

    def get_total_collected(self, obj):
        return float(obj.total_collected())

    def create(self, validated_data):
        request = self.context.get('request')
        group = Group.objects.create(created_by=request.user, **validated_data)
        # Auto-add creator as admin
        Membership.objects.create(user=request.user, group=group, role='admin', payout_position=1)
        return group


class ContributionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.UUIDField(write_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Contribution
        fields = ['id', 'user', 'user_id', 'group', 'amount', 'contribution_type',
                  'status', 'cycle_date', 'paid_date', 'due_date', 'reference_number',
                  'notes', 'is_overdue', 'created_at']
        read_only_fields = ['id', 'created_at', 'is_overdue']


class PayoutSerializer(serializers.ModelSerializer):
    recipient = UserSerializer(read_only=True)
    recipient_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Payout
        fields = ['id', 'group', 'recipient', 'recipient_id', 'round_number',
                  'amount', 'payout_date', 'actual_payout_date', 'status', 'notes']
        read_only_fields = ['id']


class GroceryItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = GroceryItem
        fields = ['id', 'name', 'quantity', 'unit', 'unit_price', 'subtotal']


class GroceryRoundSerializer(serializers.ModelSerializer):
    recipient = UserSerializer(read_only=True)
    recipient_id = serializers.UUIDField(write_only=True)
    items = GroceryItemSerializer(many=True, required=False)

    class Meta:
        model = GroceryRound
        fields = ['id', 'group', 'recipient', 'recipient_id', 'round_number',
                  'total_value', 'delivery_date', 'actual_delivery_date',
                  'status', 'notes', 'items', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        recipient_id = validated_data.pop('recipient_id')
        from .models import User
        recipient = User.objects.get(pk=recipient_id)
        gr = GroceryRound.objects.create(recipient=recipient, **validated_data)
        for item in items_data:
            GroceryItem.objects.create(grocery_round=gr, **item)
        return gr


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notification_type', 'title', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']

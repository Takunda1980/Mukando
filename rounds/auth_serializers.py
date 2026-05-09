"""
rounds/auth_serializers.py — Auth serializers (ported from FundaBiz)

Covers: registration, JWT login (with unverified-email guard),
profile read/update, and password change.
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password as dj_validate_password
from django.contrib.auth import get_user_model

User = get_user_model()


# ─── JWT LOGIN ────────────────────────────────────────────────────────────────

class MukandoTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    JWT token with user data embedded in the payload.
    Adds a clear error when the account exists but email is not yet verified,
    rather than letting Django's authenticate() swallow it as a generic 401.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['full_name'] = user.get_full_name()
        return token

    def validate(self, attrs):
        # Check email-verified BEFORE calling super() — Django's authenticate()
        # rejects inactive users with a generic 401, hiding this specific reason.
        username = attrs.get(self.username_field, '').strip()
        try:
            candidate = User.objects.get(username__iexact=username)
            if not candidate.is_active:
                raise serializers.ValidationError({
                    'detail': (
                        'Your email address has not been verified. '
                        'Please check your inbox for the verification link.'
                    )
                })
        except User.DoesNotExist:
            pass  # Wrong username — super() will raise the correct 401

        data = super().validate(attrs)

        data['user'] = {
            'id':             str(self.user.id),
            'username':       self.user.username,
            'email':          self.user.email,
            'full_name':      self.user.get_full_name(),
            'phone':          self.user.phone,
            'email_verified': self.user.email_verified,
            'avatar':         self.user.avatar.url if self.user.avatar else None,
            'preferred_language': self.user.preferred_language,
        }
        return data


# ─── REGISTRATION ─────────────────────────────────────────────────────────────

class MukandoRegisterSerializer(serializers.Serializer):
    """
    User registration.
    Creates account with is_active=False; email verification activates it.
    """
    username = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=False, default='')
    last_name = serializers.CharField(required=False, default='')
    password = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    phone = serializers.CharField(required=False, default='')
    preferred_language = serializers.ChoiceField(
        choices=['en', 'sn', 'nd'], required=False, default='en'
    )

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})

        if User.objects.filter(username__iexact=attrs['username']).exists():
            raise serializers.ValidationError({'username': 'That username is already taken.'})

        if User.objects.filter(email__iexact=attrs['email']).exists():
            raise serializers.ValidationError({'email': 'An account with this email already exists.'})

        # Enforce Django's password strength rules
        try:
            dj_validate_password(attrs['password'])
        except Exception as e:
            raise serializers.ValidationError({'password': list(e.messages)})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')

        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone', ''),
            preferred_language=validated_data.get('preferred_language', 'en'),
            is_active=False,        # inactive until email is verified
            email_verified=False,
        )
        user.set_password(password)
        user.save()
        return user


# ─── PROFILE ─────────────────────────────────────────────────────────────────

class MukandoUserProfileSerializer(serializers.ModelSerializer):
    """Full user profile — read and update."""

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'avatar', 'preferred_language', 'national_id',
            'notify_email', 'notify_sms', 'notify_whatsapp',
            'email_verified', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'email_verified', 'created_at']


# ─── CHANGE PASSWORD ──────────────────────────────────────────────────────────

class MukandoChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def validate_new_password(self, value):
        try:
            dj_validate_password(value)
        except Exception as e:
            raise serializers.ValidationError(list(e.messages))
        return value

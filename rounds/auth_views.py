"""
rounds/auth_views.py — JWT Auth Views (ported from FundaBiz)

Endpoints:
  POST   /api/auth/register/                      RegisterView
  GET    /api/auth/verify/<uidb64>/<token>/       VerifyEmailView
  POST   /api/auth/login/                         LoginView
  POST   /api/auth/logout/                        LogoutView
  POST   /api/auth/token/refresh/                 TokenRefreshView (wired in urls.py)
  POST   /api/auth/forgot-password/               ForgotPasswordView
  POST   /api/auth/reset-password/<uidb64>/<token>/ ResetPasswordView
  GET    /api/auth/profile/                       ProfileView
  PATCH  /api/auth/profile/                       ProfileView
  POST   /api/auth/change-password/               ChangePasswordView
"""

from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import AnonRateThrottle
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings

from .auth_serializers import (
    MukandoRegisterSerializer,
    MukandoTokenObtainPairSerializer,
    MukandoUserProfileSerializer,
    MukandoChangePasswordSerializer,
)
from .auth_utils import (
    send_verification_email,
    send_password_reset_email,
    get_user_from_uid,
    check_token,
)

User = get_user_model()


# ─── THROTTLE ─────────────────────────────────────────────────────────────────

class LoginRateThrottle(AnonRateThrottle):
    """Max 10 login attempts per minute per IP."""
    rate = '10/min'


# ─── REGISTRATION ─────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/

    Creates a new user with is_active=False and sends a verification email.
    JWT tokens are NOT issued until the email is verified.
    """
    queryset = User.objects.all()
    serializer_class = MukandoRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        send_verification_email(user, request)

        return Response(
            {
                'message': (
                    'Account created. Please check your email and verify '
                    'your address before logging in.'
                ),
                'user': {
                    'id':       str(user.id),
                    'username': user.username,
                    'email':    user.email,
                    'full_name': user.get_full_name(),
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ─── EMAIL VERIFICATION ───────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    """
    GET /api/auth/verify/<uidb64>/<token>/

    Activates the user account when a valid verification link is followed.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uidb64, token):
        user = get_user_from_uid(uidb64)

        if user is None or not check_token(user, token):
            return Response(
                {'error': 'Verification link is invalid or has expired.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_active and user.email_verified:
            return Response(
                {'message': 'Account is already verified. You can log in.'},
                status=status.HTTP_200_OK,
            )

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=['is_active', 'email_verified'])

        return Response(
            {'message': 'Email verified successfully. You can now log in.'},
            status=status.HTTP_200_OK,
        )


# ─── LOGIN ────────────────────────────────────────────────────────────────────

class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — JWT login with user data in response."""
    permission_classes = [permissions.AllowAny]
    serializer_class = MukandoTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


# ─── LOGOUT ───────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """POST /api/auth/logout/ — Blacklist the refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully.'})
        except Exception:
            return Response(
                {'error': 'Invalid or missing refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


# ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
    """
    POST /api/auth/forgot-password/
    Body: { "email": "user@example.com" }

    Always returns HTTP 200 regardless of whether the email exists (prevents
    email enumeration attacks).
    """
    permission_classes = [permissions.AllowAny]

    SAFE_RESPONSE = {
        'message': (
            'If an account with that email exists, you will receive a '
            'password reset link shortly.'
        )
    }

    def post(self, request):
        email = request.data.get('email', '').strip().lower()

        if not email:
            return Response(
                {'error': 'Email address is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(self.SAFE_RESPONSE, status=status.HTTP_200_OK)

        frontend_url = getattr(
            settings, 'FRONTEND_URL',
            f"{request.scheme}://{request.get_host()}"
        )
        send_password_reset_email(user, frontend_url)

        return Response(self.SAFE_RESPONSE, status=status.HTTP_200_OK)


# ─── RESET PASSWORD ───────────────────────────────────────────────────────────

class ResetPasswordView(APIView):
    """
    POST /api/auth/reset-password/<uidb64>/<token>/
    Body: { "new_password": "..." }

    Validates the token, enforces Django password rules, saves new password.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, uidb64, token):
        user = get_user_from_uid(uidb64)

        if user is None or not check_token(user, token):
            return Response(
                {'error': 'Password reset link is invalid or has expired.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_password = request.data.get('new_password', '')

        if not new_password:
            return Response(
                {'error': 'new_password is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return Response(
                {'error': list(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        return Response(
            {'message': 'Password reset successfully. You can now log in.'},
            status=status.HTTP_200_OK,
        )


# ─── PROFILE ──────────────────────────────────────────────────────────────────

class ProfileView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/profile/ — Authenticated user's own profile."""
    serializer_class = MukandoUserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ─── CHANGE PASSWORD ──────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
    """POST /api/auth/change-password/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MukandoChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'message': 'Password changed successfully.'})

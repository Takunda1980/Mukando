"""
rounds/urls.py — URL Configuration for Mukando System
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import auth_views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'groups', views.GroupViewSet, basename='group')
router.register(r'contributions', views.ContributionViewSet, basename='contribution')
router.register(r'payouts', views.PayoutViewSet, basename='payout')
router.register(r'grocery-rounds', views.GroceryRoundViewSet, basename='groceryround')
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    # ── Template Views ──────────────────────────────────────────────────
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),

    # Groups
    path('groups/', views.group_list_view, name='group_list'),
    path('groups/create/', views.create_group_view, name='create_group'),
    path('groups/join/', views.join_group_view, name='join_group'),
    path('groups/<uuid:group_id>/', views.group_detail_view, name='group_detail'),
    path('groups/<uuid:group_id>/contributions/', views.contributions_view, name='contributions'),
    path('groups/<uuid:group_id>/export-csv/', views.export_csv_view, name='export_csv'),
    path('groups/<uuid:group_id>/payout-schedule/', views.payout_schedule_view, name='payout_schedule'),
    path('groups/<uuid:group_id>/regenerate-payouts/', views.regenerate_payouts_view, name='regenerate_payouts'),

    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),

    # Transaction history & receipts
    path('transactions/', views.transaction_history_view, name='transaction_history'),
    path('paynow/receipt/<uuid:txn_id>/', views.paynow_receipt_view, name='paynow_receipt'),

    # AI Chat
    path('ai-chat/', views.ai_chat_view, name='ai_chat'),

    # PayNow Payment
    path('pay/<uuid:contribution_id>/', views.paynow_pay_view, name='paynow_pay'),
    path('paynow/return/', views.paynow_return_view, name='paynow_return'),
    path('paynow/result/', views.paynow_result_view, name='paynow_result'),
    path('paynow/status/<uuid:contribution_id>/', views.paynow_status_view, name='paynow_status'),

    # ── REST API ─────────────────────────────────────────────────────────
    path('api/', include(router.urls)),

    # ── JWT Auth (ported from FundaBiz) ──────────────────────────────────
    path('api/auth/register/',    auth_views.RegisterView.as_view(),      name='api_register'),
    path('api/auth/verify/<str:uidb64>/<str:token>/',
                                  auth_views.VerifyEmailView.as_view(),   name='api_verify_email'),
    path('api/auth/login/',       auth_views.LoginView.as_view(),         name='api_login'),
    path('api/auth/logout/',      auth_views.LogoutView.as_view(),        name='api_logout'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(),           name='token_refresh'),
    path('api/auth/forgot-password/', auth_views.ForgotPasswordView.as_view(), name='api_forgot_password'),
    path('api/auth/reset-password/<str:uidb64>/<str:token>/',
                                  auth_views.ResetPasswordView.as_view(), name='api_reset_password'),
    path('api/auth/profile/',     auth_views.ProfileView.as_view(),       name='api_profile'),
    path('api/auth/change-password/', auth_views.ChangePasswordView.as_view(), name='api_change_password'),
    path('api/ai-chat/', views.ai_chat_api, name='ai_chat_api'),
    path('api/paynow/initiate/', views.api_paynow_initiate, name='api_paynow_initiate'),
    path('api/notifications/mark-read/', views.api_mark_notifications_read, name='api_mark_notifications_read'),
]

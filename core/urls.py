from django.contrib.auth import views as auth_views
from django.urls import path

from .views import dashboard, help_manual, signup_requests, signup_view, system_settings, user_management

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('dashboard/', dashboard, name='dashboard'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True
        ),
        name='login'
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', signup_view, name='signup'),
    path('user-management/', user_management, name='user_management'),
    path('signup-requests/', signup_requests, name='signup_requests'),
    path('system-settings/', system_settings, name='system_settings'),
    path('help/', help_manual, name='help_manual'),
]

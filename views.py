from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from easy.models import Substation

from .models import UserProfile


ADMIN_ROLES = {UserProfile.ROLE_SUPER_ADMIN, UserProfile.ROLE_ADMIN}
APPROVER_ROLES = ADMIN_ROLES | {UserProfile.ROLE_APPROVER}
EDIT_ROLES = APPROVER_ROLES | {UserProfile.ROLE_DATA_ENTRY}


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserProfile.ROLE_SUPER_ADMIN
    profile = getattr(user, 'profile', None)
    if profile and profile.is_active:
        return profile.role
    return UserProfile.ROLE_VIEWER


def user_has_role(user, allowed_roles):
    return get_user_role(user) in set(allowed_roles)


def role_required(allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not user_has_role(request.user, allowed_roles):
                raise PermissionDenied('You do not have permission to access this page.')
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_allowed_substations(user):
    if not user.is_authenticated:
        return Substation.objects.none()
    if user.is_superuser or user_has_role(user, ADMIN_ROLES):
        return Substation.objects.all().order_by('substation_name')
    return Substation.objects.filter(user_accesses__user=user).distinct().order_by('substation_name')


def ensure_substation_access(user, substation):
    if substation.pk not in set(get_allowed_substations(user).values_list('pk', flat=True)):
        raise PermissionDenied('You do not have access to this substation.')

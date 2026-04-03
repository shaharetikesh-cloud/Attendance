from .permissions import ADMIN_ROLES, APPROVER_ROLES, get_allowed_substations, get_user_role


def access_flags(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'nav_role': None,
            'nav_is_admin': False,
            'nav_is_approver': False,
            'nav_allowed_substation_count': 0,
        }

    role = get_user_role(user)
    return {
        'nav_role': role,
        'nav_is_admin': role in ADMIN_ROLES,
        'nav_is_approver': role in APPROVER_ROLES,
        'nav_allowed_substation_count': get_allowed_substations(user).count(),
    }

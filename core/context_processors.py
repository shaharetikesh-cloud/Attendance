from .models import SignupRequest
from .permissions import ADMIN_ROLES, get_user_role


def admin_badge_context(request):
    if not request.user.is_authenticated:
        return {
            'pending_signup_count': 0,
        }

    role = get_user_role(request.user)
    if role in ADMIN_ROLES:
        return {
            'pending_signup_count': SignupRequest.objects.filter(
                status=SignupRequest.STATUS_PENDING
            ).count()
        }

    return {
        'pending_signup_count': 0,
    }

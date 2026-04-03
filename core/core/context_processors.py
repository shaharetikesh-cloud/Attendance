def user_access_context(request):
    if not request.user.is_authenticated:
        return {}

    profile = getattr(request.user, "userprofile", None)

    substations = []
    if profile:
        substations = profile.substations.all()

    return {
        "user_role": profile.role if profile else None,
        "user_substations": substations,
        "is_admin": request.user.is_superuser,
    }

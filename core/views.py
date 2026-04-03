from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from easy.models import (
    AdvanceShiftChart,
    AppSetting,
    ApprenticeAttendanceSheet,
    Employee,
    MonthlySheetBase,
    OperatorAttendanceSheet,
    OutsourceAttendanceSheet,
    Substation,
    TechAttendanceSheet,
)

from .forms import SignupApprovalForm, SignupForm, SimpleSettingForm, UserAccessForm, UserProfileForm
from .models import SignupRequest, UserProfile, UserSubstationAccess
from .permissions import ADMIN_ROLES, APPROVER_ROLES, get_allowed_substations, get_user_role, role_required


def _approval_required():
    return AppSetting.get_bool('approval_required', default=False)


def _self_signup_enabled():
    return AppSetting.get_bool('self_signup_enabled', default=True)


@login_required
def dashboard(request):
    allowed_substations = get_allowed_substations(request.user)
    context = {
        'role': get_user_role(request.user),
        'substation_count': allowed_substations.count(),
        'active_substation_count': allowed_substations.filter(is_active=True).count(),
        'operator_count': Employee.objects.filter(
            substation__in=allowed_substations,
            employee_type=Employee.EmployeeType.OPERATOR
        ).count(),
        'tech_count': Employee.objects.filter(
            substation__in=allowed_substations,
            employee_type=Employee.EmployeeType.TECH_ENGINEER
        ).count(),
        'operator_sheet_count': OperatorAttendanceSheet.objects.filter(substation__in=allowed_substations).count(),
        'advance_sheet_count': AdvanceShiftChart.objects.filter(substation__in=allowed_substations).count(),
        'tech_sheet_count': TechAttendanceSheet.objects.filter(substation__in=allowed_substations).count(),
        'apprentice_sheet_count': ApprenticeAttendanceSheet.objects.filter(substation__in=allowed_substations).count(),
        'outsource_sheet_count': OutsourceAttendanceSheet.objects.filter(substation__in=allowed_substations).count(),
        'pending_approval_count': 0,
        'approval_required': _approval_required(),
        'self_signup_enabled': _self_signup_enabled(),
    }

    if get_user_role(request.user) in APPROVER_ROLES:
        pending_count = 0
        for model in (
            OperatorAttendanceSheet,
            AdvanceShiftChart,
            TechAttendanceSheet,
            ApprenticeAttendanceSheet,
            OutsourceAttendanceSheet,
        ):
            pending_count += model.objects.filter(
                substation__in=allowed_substations,
                approval_status=MonthlySheetBase.STATUS_PENDING
            ).count()
        context['pending_approval_count'] = pending_count

    return render(request, 'core/dashboard.html', context)


def signup_view(request):
    if not _self_signup_enabled():
        messages.error(request, 'Self signup is disabled by admin.')
        return redirect('login')

    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                'Signup request submitted successfully. Admin approval is required before login.'
            )
            return redirect('login')
    else:
        form = SignupForm()

    return render(
        request,
        'core/signup.html',
        {
            'form': form,
            'self_signup_enabled': True,
        }
    )


@login_required
@role_required(ADMIN_ROLES)
def user_management(request):
    selected_user = None
    profile_form = None
    access_form = None

    if request.GET.get('user_id'):
        selected_user = get_object_or_404(
            User.objects.select_related('profile'),
            pk=request.GET.get('user_id')
        )

    if request.method == 'POST':
        selected_user = get_object_or_404(
            User.objects.select_related('profile'),
            pk=request.POST.get('user_id')
        )
        profile_form = UserProfileForm(request.POST, instance=selected_user.profile)
        access_form = UserAccessForm(request.POST)

        if profile_form.is_valid() and access_form.is_valid():
            profile = profile_form.save()

            selected_user.is_active = profile.is_active
            selected_user.save(update_fields=['is_active'])

            selected_ids = set(
                access_form.cleaned_data['substations'].values_list('id', flat=True)
            )

            UserSubstationAccess.objects.filter(user=selected_user).exclude(
                substation_id__in=selected_ids
            ).delete()

            existing_ids = set(
                UserSubstationAccess.objects.filter(user=selected_user).values_list('substation_id', flat=True)
            )

            for substation_id in selected_ids - existing_ids:
                UserSubstationAccess.objects.create(user=selected_user, substation_id=substation_id)

            messages.success(request, 'User role and substation access updated successfully.')
            return redirect(f"{request.path}?user_id={selected_user.pk}")

    if selected_user and not profile_form:
        profile_form = UserProfileForm(instance=selected_user.profile)
        access_form = UserAccessForm(
            initial={
                'substations': UserSubstationAccess.objects.filter(user=selected_user).values_list('substation_id', flat=True)
            }
        )

    users = User.objects.select_related('profile').order_by('username')

    return render(
        request,
        'core/user_management.html',
        {
            'users': users,
            'selected_user': selected_user,
            'profile_form': profile_form,
            'access_form': access_form,
        }
    )


@login_required
@role_required(ADMIN_ROLES)
def signup_requests(request):
    if request.method == 'POST':
        signup_request = get_object_or_404(
            SignupRequest.objects.select_related('user', 'user__profile'),
            pk=request.POST.get('request_id')
        )
        form = SignupApprovalForm(request.POST)

        if form.is_valid():
            action = form.cleaned_data['action']
            profile = signup_request.user.profile

            profile.role = form.cleaned_data['role']
            profile.mobile_no = signup_request.mobile_no or profile.mobile_no
            profile.is_active = action == 'approve'
            profile.save()

            signup_request.user.is_active = action == 'approve'
            signup_request.user.save(update_fields=['is_active'])

            signup_request.status = (
                SignupRequest.STATUS_APPROVED
                if action == 'approve'
                else SignupRequest.STATUS_REJECTED
            )
            signup_request.admin_remark = form.cleaned_data['admin_remark']
            signup_request.save(update_fields=['status', 'admin_remark', 'updated_at'])

            UserSubstationAccess.objects.filter(user=signup_request.user).delete()
            for substation in form.cleaned_data['substations']:
                UserSubstationAccess.objects.create(user=signup_request.user, substation=substation)

            messages.success(
                request,
                f'Signup request {signup_request.get_status_display().lower()} successfully.'
            )
            return redirect('signup_requests')
    else:
        form = SignupApprovalForm()

    requests_qs = SignupRequest.objects.select_related('user', 'requested_substation').all()

    return render(
        request,
        'core/signup_requests.html',
        {
            'requests': requests_qs,
            'approval_form': form,
        }
    )


@login_required
@role_required(ADMIN_ROLES)
def system_settings(request):
    if request.method == 'POST':
        form = SimpleSettingForm(request.POST)
        if form.is_valid():
            AppSetting.set_value(
                'self_signup_enabled',
                'true' if form.cleaned_data['self_signup_enabled'] else 'false'
            )
            AppSetting.set_value(
                'approval_required',
                'true' if form.cleaned_data['approval_required'] else 'false'
            )
            messages.success(request, 'System settings updated successfully.')
            return redirect('system_settings')
    else:
        form = SimpleSettingForm(
            initial={
                'self_signup_enabled': _self_signup_enabled(),
                'approval_required': _approval_required(),
            }
        )

    return render(request, 'core/system_settings.html', {'form': form})


@login_required
def help_manual(request):
    return render(request, 'core/help_manual.html')

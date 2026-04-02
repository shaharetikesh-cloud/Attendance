import os
from datetime import timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone as dj_timezone

from core.permissions import APPROVER_ROLES, EDIT_ROLES, get_allowed_substations, get_user_role, ensure_substation_access

from .forms import (
    AdvanceShiftForm,
    ApprenticeAttendanceForm,
    EmployeeForm,
    OperatorChartForm,
    OutsourceAttendanceForm,
    SubstationForm,
    TechAttendanceForm,
)
from .models import (
    AdvanceShiftChart,
    AdvanceShiftRow,
    AppSetting,
    ApprenticeAttendanceRow,
    ApprenticeAttendanceSheet,
    EasyNightAllowanceEntry,
    Employee,
    MonthlySheetBase,
    OperatorAttendanceRow,
    OperatorAttendanceSheet,
    OutsourceAttendanceRow,
    OutsourceAttendanceSheet,
    Substation,
    TechAttendanceRow,
    TechAttendanceSheet,
)
from .services import (
    ATTENDANCE_BLANK,
    ATTENDANCE_OFF,
    SHIFT_OFF,
    build_day_headers,
    build_night_allowance_rows,
    build_report_remark_lines,
    calculate_night_allowance_amount,
    generate_advance_shift_chart,
    generate_apprentice_attendance,
    generate_leave_remarks,
    generate_operator_chart,
    generate_outsource_attendance,
    generate_tech_attendance,
    get_attendance_choices,
    get_night_allowance_rate,
    load_advance_sheet_rows,
    load_apprentice_sheet_rows,
    load_operator_sheet_rows,
    load_outsource_sheet_rows,
    load_tech_sheet_rows,
    month_year_label,
    normalize_attendance_value,
)

PDF_STYLESHEET = (Path(settings.STATICFILES_DIRS[0]) / 'css' / 'pdf.css').as_uri()
WEASYPRINT_DLL_HANDLES = []


SHEET_MODEL_LABELS = {
    OperatorAttendanceSheet: 'Operator Attendance',
    AdvanceShiftChart: 'Advance Shift',
    TechAttendanceSheet: 'Tech Attendance',
    ApprenticeAttendanceSheet: 'Apprentice Attendance',
    OutsourceAttendanceSheet: 'Outsource Attendance',
}


def approval_required():
    return AppSetting.get_bool('approval_required', default=False)


def _selected_period(form):
    substation = form.cleaned_data['substation']
    return substation, int(form.cleaned_data['month']), form.cleaned_data['year']


def _configure_weasyprint_windows_dlls():
    if os.name != 'nt' or not hasattr(os, 'add_dll_directory'):
        return
    candidate_roots = []
    env_root = os.environ.get('MSEDCL_MSYS2_ROOT')
    if env_root:
        candidate_roots.append(Path(env_root))
    candidate_roots.extend([settings.BASE_DIR.parent.parent, Path(r'E:\Attendance software')])
    checked = set()
    for root in candidate_roots:
        for variant in ('mingw64', 'ucrt64', 'clang64'):
            dll_dir = (Path(root) / variant / 'bin').resolve()
            if dll_dir in checked or not dll_dir.exists():
                continue
            checked.add(dll_dir)
            WEASYPRINT_DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))


def _build_rows_for_template(rows, day_headers, include_attendance=False, include_shift=False):
    prepared_rows = []
    for index, row in enumerate(rows, start=1):
        prepared = {**row, 'sr_no': index}
        if include_attendance:
            attendance_default = ATTENDANCE_BLANK if row.get('is_vacant') else ATTENDANCE_OFF
            prepared['attendance_cells'] = [
                {'day': day['day'], 'value': row['attendance_days'].get(str(day['day']), attendance_default)}
                for day in day_headers
            ]
            prepared['attendance_choices'] = get_attendance_choices(include_blank=row.get('is_vacant', False))
        if include_shift:
            prepared['shift_cells'] = [
                {'day': day['day'], 'value': row['shift_days'].get(str(day['day']), SHIFT_OFF)} for day in day_headers
            ]
        prepared_rows.append(prepared)
    return prepared_rows


def _operator_chart_context(chart_data, substation=None, night_allowance_rows=None, manual_remark=''):
    leave_remarks = chart_data.get('leave_remarks')
    if leave_remarks is None:
        leave_remarks = generate_leave_remarks(chart_data['rows'], chart_data['days'])
    rate = get_night_allowance_rate(substation) if substation else Decimal('190.00')
    return {
        'days': chart_data['days'],
        'rows': _build_rows_for_template(chart_data['rows'], chart_data['days'], include_attendance=True, include_shift=True),
        'night_allowance_rows': night_allowance_rows or chart_data.get('night_allowance_rows') or build_night_allowance_rows(chart_data['rows'], default_rate=rate),
        'attendance_choices': get_attendance_choices(),
        'leave_remarks': leave_remarks,
        'report_remark_lines': build_report_remark_lines(leave_remarks, manual_remark),
        'warnings': chart_data.get('warnings', []),
    }


def _advance_chart_context(chart_data):
    return {
        'days': chart_data['days'],
        'rows': _build_rows_for_template(chart_data['rows'], chart_data['days'], include_shift=True),
        'warnings': chart_data.get('warnings', []),
    }


def _simple_attendance_context(chart_data, manual_remark=''):
    leave_remarks = chart_data.get('leave_remarks')
    if leave_remarks is None:
        leave_remarks = generate_leave_remarks(chart_data['rows'], chart_data['days'])
    return {
        'days': chart_data['days'],
        'rows': _build_rows_for_template(chart_data['rows'], chart_data['days'], include_attendance=True),
        'attendance_choices': get_attendance_choices(),
        'leave_remarks': leave_remarks,
        'report_remark_lines': build_report_remark_lines(leave_remarks, manual_remark),
        'warnings': chart_data.get('warnings', []),
    }


def _parse_operator_rows(post_data, day_headers):
    rows = []
    try:
        total_rows = int(post_data.get('row_total', 0) or 0)
    except (TypeError, ValueError):
        total_rows = 0
    for index in range(total_rows):
        employee_name = post_data.get(f'row_{index}_employee_name', '').strip()
        if not employee_name:
            continue
        row_is_vacant = post_data.get(f'row_{index}_is_vacant', '').strip().lower() in {'1', 'true', 'yes', 'on'}
        row = {
            'employee_id': post_data.get(f'row_{index}_employee_id') or None,
            'employee_name': employee_name,
            'designation_short': post_data.get(f'row_{index}_designation_short', '').strip(),
            'cpf_no': post_data.get(f'row_{index}_cpf_no', '').strip(),
            'working_place': post_data.get(f'row_{index}_working_place', '').strip(),
            'is_vacant': row_is_vacant,
            'attendance_days': {},
            'shift_days': {},
        }
        for day in day_headers:
            day_key = str(day['day'])
            row['attendance_days'][day_key] = normalize_attendance_value(
                post_data.get(f'row_{index}_attendance_{day_key}', ATTENDANCE_BLANK if row_is_vacant else ATTENDANCE_OFF),
                ATTENDANCE_BLANK if row_is_vacant else ATTENDANCE_OFF,
                allow_blank=row_is_vacant,
            )
            row['shift_days'][day_key] = post_data.get(f'row_{index}_shift_{day_key}', SHIFT_OFF)
        rows.append(row)
    return rows


def _parse_night_allowance_rows(post_data):
    rows = []
    try:
        total_rows = int(post_data.get('night_allowance_total', 0) or 0)
    except (TypeError, ValueError):
        total_rows = 0
    for index in range(total_rows):
        display_name = post_data.get(f'night_{index}_display_name', '').strip()
        if not display_name:
            continue
        night_count_raw = post_data.get(f'night_{index}_night_count', '').strip()
        rate_raw = post_data.get(f'night_{index}_rate', '').strip()
        try:
            night_count = int(night_count_raw) if night_count_raw else None
            rate = Decimal(rate_raw) if rate_raw else None
        except (TypeError, ValueError, InvalidOperation):
            raise ValueError('Night allowance values must be valid numbers.')
        rows.append(
            {
                'serial_no': int(post_data.get(f'night_{index}_serial_no', index + 1)),
                'employee_id': post_data.get(f'night_{index}_employee_id') or None,
                'display_name': display_name,
                'night_count': night_count,
                'rate': rate,
                'amount': calculate_night_allowance_amount(night_count, rate),
                'remark': post_data.get(f'night_{index}_remark', '').strip(),
            }
        )
    return rows


def _parse_advance_rows(post_data, day_headers):
    rows = []
    try:
        total_rows = int(post_data.get('row_total', 0) or 0)
    except (TypeError, ValueError):
        total_rows = 0
    for index in range(total_rows):
        employee_name = post_data.get(f'row_{index}_employee_name', '').strip()
        if not employee_name:
            continue
        row = {
            'employee_id': post_data.get(f'row_{index}_employee_id') or None,
            'employee_name': employee_name,
            'designation_short': post_data.get(f'row_{index}_designation_short', '').strip(),
            'cpf_no': post_data.get(f'row_{index}_cpf_no', '').strip(),
            'working_place': post_data.get(f'row_{index}_working_place', '').strip(),
            'shift_days': {},
        }
        for day in day_headers:
            day_key = str(day['day'])
            row['shift_days'][day_key] = post_data.get(f'row_{index}_shift_{day_key}', SHIFT_OFF)
        rows.append(row)
    return rows


def _parse_attendance_rows(post_data, day_headers):
    rows = []
    try:
        total_rows = int(post_data.get('row_total', 0) or 0)
    except (TypeError, ValueError):
        total_rows = 0
    for index in range(total_rows):
        employee_name = post_data.get(f'row_{index}_employee_name', '').strip()
        if not employee_name:
            continue
        row = {
            'employee_id': post_data.get(f'row_{index}_employee_id') or None,
            'employee_name': employee_name,
            'designation_short': post_data.get(f'row_{index}_designation_short', '').strip(),
            'cpf_no': post_data.get(f'row_{index}_cpf_no', '').strip(),
            'working_place': post_data.get(f'row_{index}_working_place', '').strip(),
            'attendance_days': {},
        }
        for day in day_headers:
            day_key = str(day['day'])
            row['attendance_days'][day_key] = normalize_attendance_value(post_data.get(f'row_{index}_attendance_{day_key}', ATTENDANCE_OFF), ATTENDANCE_OFF)
        rows.append(row)
    return rows


def _operator_sheet_queryset(substation, month, year):
    return OperatorAttendanceSheet.objects.filter(substation=substation, month=month, year=year)


def _advance_sheet_queryset(substation, month, year):
    return AdvanceShiftChart.objects.filter(substation=substation, month=month, year=year)


def _tech_sheet_queryset(substation, month, year):
    return TechAttendanceSheet.objects.filter(substation=substation, month=month, year=year)


def _simple_sheet_queryset(sheet_model, substation, month, year):
    return sheet_model.objects.filter(substation=substation, month=month, year=year)


def _set_sheet_save_status(sheet, request, action):
    role = get_user_role(request.user)
    now = dj_timezone.now()
    sheet.approval_remark = ''

    if not approval_required():
        sheet.approval_status = MonthlySheetBase.STATUS_APPROVED
        sheet.submitted_by = request.user
        sheet.approved_by = request.user
        sheet.submitted_at = now
        sheet.approved_at = now
        return

    if action == 'submit':
        sheet.approval_status = MonthlySheetBase.STATUS_PENDING
        sheet.submitted_by = request.user
        sheet.submitted_at = now
        sheet.approved_by = None
        sheet.approved_at = None
        if role in APPROVER_ROLES:
            sheet.approval_status = MonthlySheetBase.STATUS_APPROVED
            sheet.approved_by = request.user
            sheet.approved_at = now
    else:
        sheet.approval_status = MonthlySheetBase.STATUS_DRAFT
        sheet.submitted_by = request.user
        sheet.submitted_at = now
        sheet.approved_by = None
        sheet.approved_at = None
        if role in APPROVER_ROLES:
            sheet.approval_status = MonthlySheetBase.STATUS_APPROVED
            sheet.approved_by = request.user
            sheet.approved_at = now


def _user_can_modify_sheets(user):
    return get_user_role(user) in EDIT_ROLES


def _ensure_sheet_modify_permission(request, action):
    if action not in {'save', 'submit'}:
        return True
    if _user_can_modify_sheets(request.user):
        return True
    messages.error(request, 'You have view-only access. Save or submit is allowed only for data entry, approver, or admin users.')
    return False


def _approval_message(sheet):
    mapping = {
        MonthlySheetBase.STATUS_DRAFT: 'Saved as draft.',
        MonthlySheetBase.STATUS_PENDING: 'Submitted for approval.',
        MonthlySheetBase.STATUS_APPROVED: 'Saved and approved successfully.',
        MonthlySheetBase.STATUS_REJECTED: 'Sheet is rejected.',
    }
    return mapping.get(sheet.approval_status, 'Saved successfully.')


def _can_edit_sheet(request, sheet):
    if not sheet:
        return True
    role = get_user_role(request.user)
    return sheet.approval_status != MonthlySheetBase.STATUS_APPROVED or role in APPROVER_ROLES


@login_required
def substation_master(request, substation_id=None, employee_id=None):
    selected_substation = None
    editing_substation = None
    editing_employee = None
    allowed_substations = get_allowed_substations(request.user)

    if substation_id:
        editing_substation = get_object_or_404(allowed_substations, pk=substation_id)
        selected_substation = editing_substation
    if employee_id:
        editing_employee = get_object_or_404(Employee.objects.filter(substation__in=allowed_substations), pk=employee_id)
        selected_substation = editing_employee.substation
    if request.GET.get('substation') and not selected_substation:
        selected_substation = allowed_substations.filter(pk=request.GET.get('substation')).first()

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'substation':
            if get_user_role(request.user) not in APPROVER_ROLES:
                messages.error(request, 'Only admin or approver level users can manage substation master.')
                return redirect('dashboard')
            instance = get_object_or_404(allowed_substations, pk=request.POST.get('substation_id')) if request.POST.get('substation_id') else None
            substation_form = SubstationForm(request.POST, instance=instance)
            employee_form = EmployeeForm(selected_substation=selected_substation, user=request.user)
            if substation_form.is_valid():
                saved_substation = substation_form.save()
                messages.success(request, 'Substation details saved successfully.')
                return redirect(f'{request.path}?substation={saved_substation.pk}')
        else:
            if get_user_role(request.user) not in APPROVER_ROLES:
                messages.error(request, 'Only admin or approver level users can manage employee master.')
                return redirect('dashboard')
            instance = get_object_or_404(Employee.objects.filter(substation__in=allowed_substations), pk=request.POST.get('employee_id')) if request.POST.get('employee_id') else None
            selected_substation = get_object_or_404(allowed_substations, pk=request.POST.get('substation'))
            employee_form = EmployeeForm(request.POST, instance=instance, selected_substation=selected_substation, user=request.user)
            substation_form = SubstationForm(instance=selected_substation if editing_substation else None)
            if employee_form.is_valid():
                employee = employee_form.save()
                operator_count = employee.substation.employees.filter(employee_type=Employee.EmployeeType.OPERATOR).count()
                messages.success(request, 'Employee details saved successfully.')
                if operator_count > 4:
                    messages.warning(request, 'Soft rule reminder: keep maximum 4 operators per substation.')
                return redirect(f'{request.path}?substation={employee.substation.pk}')
    else:
        substation_form = SubstationForm(instance=editing_substation)
        employee_form = EmployeeForm(instance=editing_employee, selected_substation=selected_substation, user=request.user)

    substations = allowed_substations.prefetch_related('employees').order_by('substation_name')
    employee_list = selected_substation.employees.order_by('id') if selected_substation else Employee.objects.none()
    context = {
        'substation_form': substation_form,
        'employee_form': employee_form,
        'selected_substation': selected_substation,
        'substations': substations,
        'employee_list': employee_list,
        'editing_substation': editing_substation,
        'editing_employee': editing_employee,
        'can_manage_master': get_user_role(request.user) in APPROVER_ROLES,
    }
    return render(request, 'easy/substation_master.html', context)


@login_required
def substation_delete(request, substation_id):
    if get_user_role(request.user) not in APPROVER_ROLES:
        messages.error(request, 'Only admin or approver level users can delete substations.')
        return redirect('easy:substation_master')
    substation = get_object_or_404(get_allowed_substations(request.user), pk=substation_id)
    if request.method == 'POST':
        substation.delete()
        messages.success(request, 'Substation deleted successfully.')
        return redirect('easy:substation_master')
    return redirect(f"{redirect('easy:substation_master').url}?substation={substation.pk}")


@login_required
def employee_delete(request, employee_id):
    if get_user_role(request.user) not in APPROVER_ROLES:
        messages.error(request, 'Only admin or approver level users can delete employees.')
        return redirect('easy:substation_master')
    employee = get_object_or_404(Employee.objects.filter(substation__in=get_allowed_substations(request.user)), pk=employee_id)
    substation_id = employee.substation_id
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted successfully.')
    return redirect(f"{redirect('easy:substation_master').url}?substation={substation_id}")


@login_required
def approval_queue(request):
    if get_user_role(request.user) not in APPROVER_ROLES:
        messages.error(request, 'You do not have approval permission.')
        return redirect('dashboard')

    if request.method == 'POST':
        model_name = request.POST.get('model_name')
        sheet_id = request.POST.get('sheet_id')
        action = request.POST.get('action')
        remark = request.POST.get('approval_remark', '').strip()
        model_map = {
            'operator': OperatorAttendanceSheet,
            'advance': AdvanceShiftChart,
            'tech': TechAttendanceSheet,
            'apprentice': ApprenticeAttendanceSheet,
            'outsource': OutsourceAttendanceSheet,
        }
        model = model_map.get(model_name)
        if model:
            sheet = get_object_or_404(model.objects.filter(substation__in=get_allowed_substations(request.user)), pk=sheet_id)
            if action == 'approve':
                sheet.approval_status = MonthlySheetBase.STATUS_APPROVED
                sheet.approved_by = request.user
                sheet.approved_at = dj_timezone.now()
                sheet.approval_remark = remark
                sheet.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'approval_remark', 'updated_at'])
                messages.success(request, f'{SHEET_MODEL_LABELS[model]} approved successfully.')
            elif action == 'reject':
                sheet.approval_status = MonthlySheetBase.STATUS_REJECTED
                sheet.approved_by = request.user
                sheet.approved_at = dj_timezone.now()
                sheet.approval_remark = remark
                sheet.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'approval_remark', 'updated_at'])
                messages.warning(request, f'{SHEET_MODEL_LABELS[model]} rejected.')
        return redirect('easy:approval_queue')

    allowed_substations = get_allowed_substations(request.user)
    pending_items = []
    for slug, model in [('operator', OperatorAttendanceSheet), ('advance', AdvanceShiftChart), ('tech', TechAttendanceSheet), ('apprentice', ApprenticeAttendanceSheet), ('outsource', OutsourceAttendanceSheet)]:
        for sheet in model.objects.filter(substation__in=allowed_substations, approval_status__in=[MonthlySheetBase.STATUS_PENDING, MonthlySheetBase.STATUS_REJECTED]).order_by('-updated_at'):
            pending_items.append({'model_name': slug, 'label': SHEET_MODEL_LABELS[model], 'sheet': sheet})
    pending_items.sort(key=lambda item: item['sheet'].updated_at, reverse=True)
    return render(request, 'easy/approval_queue.html', {'pending_items': pending_items, 'approval_required': approval_required()})


def _build_sheet_status_context(request, sheet):
    can_modify = _user_can_modify_sheets(request.user)
    can_edit_current_sheet = can_modify and _can_edit_sheet(request, sheet)
    return {
        'approval_required': approval_required(),
        'sheet_status': getattr(sheet, 'approval_status', ''),
        'sheet_status_display': getattr(sheet, 'get_approval_status_display', lambda: '')(),
        'sheet_approval_remark': getattr(sheet, 'approval_remark', ''),
        'can_modify_sheet': can_modify,
        'can_edit_current_sheet': can_edit_current_sheet,
    }


@login_required
def operator_chart(request):
    chart = None
    sheet = None
    if request.method == 'POST':
        form = OperatorChartForm(request.POST, user=request.user)
        if form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            action = request.POST.get('action')
            if not _ensure_sheet_modify_permission(request, action):
                pass
            elif action == 'generate':
                chart_data = generate_operator_chart(substation, year, month)
                chart = _operator_chart_context(chart_data, substation=substation, manual_remark=form.cleaned_data.get('remark', ''))
                sheet = _operator_sheet_queryset(substation, month, year).first()
            elif action in {'save', 'submit'}:
                sheet = _operator_sheet_queryset(substation, month, year).first()
                if sheet and not _can_edit_sheet(request, sheet):
                    messages.error(request, 'Approved sheet is locked. Only approver/admin can edit it.')
                else:
                    day_headers = build_day_headers(year, month)
                    rows = _parse_operator_rows(request.POST, day_headers)
                    try:
                        allowance_rows = _parse_night_allowance_rows(request.POST)
                    except ValueError as exc:
                        messages.error(request, str(exc))
                        allowance_rows = None
                    if not rows:
                        messages.error(request, 'Generate the operator chart before saving.')
                    elif allowance_rows is None:
                        pass
                    else:
                        with transaction.atomic():
                            sheet, _ = OperatorAttendanceSheet.objects.get_or_create(substation=substation, month=month, year=year)
                            sheet.certificate_text = form.cleaned_data.get('certificate_text', '')
                            sheet.remark = form.cleaned_data.get('remark', '')
                            _set_sheet_save_status(sheet, request, action)
                            sheet.save()
                            sheet.rows.all().delete()
                            sheet.night_allowance_entries.all().delete()
                            for order, row in enumerate(rows, start=1):
                                OperatorAttendanceRow.objects.create(
                                    sheet=sheet,
                                    employee_id=row['employee_id'] or None,
                                    employee_name=row['employee_name'],
                                    designation_short=row['designation_short'],
                                    cpf_no=row['cpf_no'],
                                    working_place=row['working_place'],
                                    is_vacant=row['is_vacant'],
                                    attendance_days=row['attendance_days'],
                                    shift_days=row['shift_days'],
                                    sort_order=order,
                                )
                            for allowance_row in allowance_rows:
                                EasyNightAllowanceEntry.objects.create(
                                    operator_month=sheet,
                                    employee_id=allowance_row['employee_id'] or None,
                                    display_name=allowance_row['display_name'],
                                    serial_no=allowance_row['serial_no'],
                                    night_count=allowance_row['night_count'],
                                    rate=allowance_row['rate'],
                                    remark=allowance_row['remark'],
                                )
                            sheet.sync_night_allowance_summary()
                            sheet.save(update_fields=['night_shift_allowance_units', 'night_shift_rate', 'updated_at'])
                        messages.success(request, _approval_message(sheet))
                        return redirect(f'{request.path}?substation={substation.pk}&month={month}&year={year}')
    else:
        form = OperatorChartForm(request.GET or None, user=request.user)
        if request.GET and form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            sheet = _operator_sheet_queryset(substation, month, year).first()
            if sheet:
                chart = _operator_chart_context(load_operator_sheet_rows(sheet), substation=substation, manual_remark=sheet.remark)
                initial = request.GET.copy()
                initial['certificate_text'] = sheet.certificate_text
                initial['remark'] = sheet.remark
                form = OperatorChartForm(initial=initial, user=request.user)
        elif not request.GET:
            form = OperatorChartForm(user=request.user)
    month_label = None
    if form.is_bound and form.is_valid():
        _, month, year = _selected_period(form)
        month_label = month_year_label(year, month)
    context = {'form': form, 'chart': chart, 'sheet': sheet, 'month_label': month_label, **_build_sheet_status_context(request, sheet)}
    return render(request, 'easy/operator_chart.html', context)


@login_required
def advance_shift_chart(request):
    chart = None
    sheet = None
    if request.method == 'POST':
        form = AdvanceShiftForm(request.POST, user=request.user)
        if form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            action = request.POST.get('action')
            if not _ensure_sheet_modify_permission(request, action):
                pass
            elif action == 'generate':
                chart = _advance_chart_context(generate_advance_shift_chart(substation, year, month))
                sheet = _advance_sheet_queryset(substation, month, year).first()
            elif action in {'save', 'submit'}:
                sheet = _advance_sheet_queryset(substation, month, year).first()
                if sheet and not _can_edit_sheet(request, sheet):
                    messages.error(request, 'Approved sheet is locked. Only approver/admin can edit it.')
                else:
                    rows = _parse_advance_rows(request.POST, build_day_headers(year, month))
                    if not rows:
                        messages.error(request, 'Generate the advance shift chart before saving.')
                    else:
                        with transaction.atomic():
                            sheet, _ = AdvanceShiftChart.objects.get_or_create(substation=substation, month=month, year=year)
                            sheet.certificate_text = form.cleaned_data.get('certificate_text', '')
                            sheet.remark = form.cleaned_data.get('remark', '')
                            _set_sheet_save_status(sheet, request, action)
                            sheet.save()
                            sheet.rows.all().delete()
                            for order, row in enumerate(rows, start=1):
                                AdvanceShiftRow.objects.create(sheet=sheet, employee_id=row['employee_id'] or None, employee_name=row['employee_name'], designation_short=row['designation_short'], cpf_no=row['cpf_no'], working_place=row['working_place'], shift_days=row['shift_days'], sort_order=order)
                        messages.success(request, _approval_message(sheet))
                        return redirect(f'{request.path}?substation={substation.pk}&month={month}&year={year}')
    else:
        form = AdvanceShiftForm(request.GET or None, user=request.user)
        if request.GET and form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            sheet = _advance_sheet_queryset(substation, month, year).first()
            if sheet:
                chart = _advance_chart_context(load_advance_sheet_rows(sheet))
                initial = request.GET.copy()
                initial['certificate_text'] = sheet.certificate_text
                initial['remark'] = sheet.remark
                form = AdvanceShiftForm(initial=initial, user=request.user)
        elif not request.GET:
            form = AdvanceShiftForm(user=request.user)
    month_label = None
    if form.is_bound and form.is_valid():
        _, month, year = _selected_period(form)
        month_label = month_year_label(year, month)
    return render(request, 'easy/advance_shift_chart.html', {'form': form, 'chart': chart, 'sheet': sheet, 'month_label': month_label, **_build_sheet_status_context(request, sheet)})


def _simple_attendance_view(request, *, form_class, sheet_model, row_model, generate_chart, load_chart, template_name, success_message, empty_chart_message):
    chart = None
    sheet = None
    if request.method == 'POST':
        form = form_class(request.POST, user=request.user)
        if form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            action = request.POST.get('action')
            if not _ensure_sheet_modify_permission(request, action):
                pass
            elif action == 'generate':
                chart = _simple_attendance_context(generate_chart(substation, year, month), manual_remark=form.cleaned_data.get('remark', ''))
                sheet = _simple_sheet_queryset(sheet_model, substation, month, year).first()
            elif action in {'save', 'submit'}:
                sheet = _simple_sheet_queryset(sheet_model, substation, month, year).first()
                if sheet and not _can_edit_sheet(request, sheet):
                    messages.error(request, 'Approved sheet is locked. Only approver/admin can edit it.')
                else:
                    rows = _parse_attendance_rows(request.POST, build_day_headers(year, month))
                    if not rows:
                        messages.error(request, empty_chart_message)
                    else:
                        with transaction.atomic():
                            sheet, _ = sheet_model.objects.get_or_create(substation=substation, month=month, year=year)
                            sheet.certificate_text = form.cleaned_data.get('certificate_text', '')
                            sheet.remark = form.cleaned_data.get('remark', '')
                            _set_sheet_save_status(sheet, request, action)
                            sheet.save()
                            sheet.rows.all().delete()
                            for order, row in enumerate(rows, start=1):
                                row_model.objects.create(sheet=sheet, employee_id=row['employee_id'] or None, employee_name=row['employee_name'], designation_short=row['designation_short'], cpf_no=row['cpf_no'], working_place=row['working_place'], attendance_days=row['attendance_days'], sort_order=order)
                        messages.success(request, _approval_message(sheet) if approval_required() else success_message)
                        return redirect(f'{request.path}?substation={substation.pk}&month={month}&year={year}')
    else:
        form = form_class(request.GET or None, user=request.user)
        if request.GET and form.is_valid():
            substation, month, year = _selected_period(form)
            ensure_substation_access(request.user, substation)
            sheet = _simple_sheet_queryset(sheet_model, substation, month, year).first()
            if sheet:
                chart = _simple_attendance_context(load_chart(sheet), manual_remark=sheet.remark)
                initial = request.GET.copy()
                initial['certificate_text'] = sheet.certificate_text
                initial['remark'] = sheet.remark
                form = form_class(initial=initial, user=request.user)
        elif not request.GET:
            form = form_class(user=request.user)
    month_label = None
    if form.is_bound and form.is_valid():
        _, month, year = _selected_period(form)
        month_label = month_year_label(year, month)
    return render(request, template_name, {'form': form, 'chart': chart, 'sheet': sheet, 'month_label': month_label, **_build_sheet_status_context(request, sheet)})


@login_required
def tech_attendance(request):
    return _simple_attendance_view(request, form_class=TechAttendanceForm, sheet_model=TechAttendanceSheet, row_model=TechAttendanceRow, generate_chart=generate_tech_attendance, load_chart=load_tech_sheet_rows, template_name='easy/tech_attendance.html', success_message='Tech and engineer attendance saved successfully.', empty_chart_message='Generate the tech attendance sheet before saving.')


@login_required
def apprentice_attendance(request):
    return _simple_attendance_view(request, form_class=ApprenticeAttendanceForm, sheet_model=ApprenticeAttendanceSheet, row_model=ApprenticeAttendanceRow, generate_chart=generate_apprentice_attendance, load_chart=load_apprentice_sheet_rows, template_name='easy/apprentice_attendance.html', success_message='Apprentice attendance saved successfully.', empty_chart_message='Generate the apprentice attendance sheet before saving.')


@login_required
def outsource_attendance(request):
    return _simple_attendance_view(request, form_class=OutsourceAttendanceForm, sheet_model=OutsourceAttendanceSheet, row_model=OutsourceAttendanceRow, generate_chart=generate_outsource_attendance, load_chart=load_outsource_sheet_rows, template_name='easy/outsource_attendance.html', success_message='Outsource attendance saved successfully.', empty_chart_message='Generate the outsource attendance sheet before saving.')


def _render_pdf(request, template_name, context, filename):
    try:
        _configure_weasyprint_windows_dlls()
        from weasyprint import HTML
        html_string = render_to_string(template_name, context)
        pdf_bytes = HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf()
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except (ImportError, OSError) as exc:
        return render(request, 'easy/pdf_unavailable.html', {'dependency_error': str(exc), 'back_url': request.META.get('HTTP_REFERER') or '/dashboard/'}, status=503)


def _can_view_pdf(request, sheet):
    ensure_substation_access(request.user, sheet.substation)
    if not approval_required():
        return True
    if sheet.approval_status == MonthlySheetBase.STATUS_APPROVED:
        return True
    if get_user_role(request.user) in APPROVER_ROLES:
        return True
    messages.error(request, 'PDF is available after approval only.')
    return False


@login_required
def operator_chart_pdf(request, sheet_id):
    sheet = get_object_or_404(OperatorAttendanceSheet, pk=sheet_id)
    if not _can_view_pdf(request, sheet):
        return redirect('easy:operator_chart')
    chart = _operator_chart_context(load_operator_sheet_rows(sheet), substation=sheet.substation, manual_remark=sheet.remark)
    context = {'sheet': sheet, 'chart': chart, 'month_label': sheet.month_year_label, 'pdf_stylesheet': PDF_STYLESHEET}
    filename = f'operator-duty-chart-{sheet.substation.substation_name}-{sheet.month}-{sheet.year}.pdf'
    return _render_pdf(request, 'easy/pdf/operator_chart_pdf.html', context, filename)


@login_required
def advance_shift_chart_pdf(request, sheet_id):
    sheet = get_object_or_404(AdvanceShiftChart, pk=sheet_id)
    if not _can_view_pdf(request, sheet):
        return redirect('easy:advance_shift_chart')
    chart = _advance_chart_context(load_advance_sheet_rows(sheet))
    context = {'sheet': sheet, 'chart': chart, 'month_label': sheet.month_year_label, 'pdf_stylesheet': PDF_STYLESHEET}
    filename = f'advance-shift-chart-{sheet.substation.substation_name}-{sheet.month}-{sheet.year}.pdf'
    return _render_pdf(request, 'easy/pdf/advance_shift_chart_pdf.html', context, filename)


def _simple_attendance_pdf(request, sheet_id, *, sheet_model, load_chart, template_name, filename_prefix, back_url):
    sheet = get_object_or_404(sheet_model, pk=sheet_id)
    if not _can_view_pdf(request, sheet):
        return redirect(back_url)
    chart = _simple_attendance_context(load_chart(sheet), manual_remark=sheet.remark)
    context = {'sheet': sheet, 'chart': chart, 'month_label': sheet.month_year_label, 'pdf_stylesheet': PDF_STYLESHEET}
    filename = f'{filename_prefix}-{sheet.substation.substation_name}-{sheet.month}-{sheet.year}.pdf'
    return _render_pdf(request, template_name, context, filename)


@login_required
def tech_attendance_pdf(request, sheet_id):
    return _simple_attendance_pdf(request, sheet_id, sheet_model=TechAttendanceSheet, load_chart=load_tech_sheet_rows, template_name='easy/pdf/tech_attendance_pdf.html', filename_prefix='tech-attendance', back_url='easy:tech_attendance')


@login_required
def apprentice_attendance_pdf(request, sheet_id):
    return _simple_attendance_pdf(request, sheet_id, sheet_model=ApprenticeAttendanceSheet, load_chart=load_apprentice_sheet_rows, template_name='easy/pdf/apprentice_attendance_pdf.html', filename_prefix='apprentice-attendance', back_url='easy:apprentice_attendance')


@login_required
def outsource_attendance_pdf(request, sheet_id):
    return _simple_attendance_pdf(request, sheet_id, sheet_model=OutsourceAttendanceSheet, load_chart=load_outsource_sheet_rows, template_name='easy/pdf/outsource_attendance_pdf.html', filename_prefix='outsource-attendance', back_url='easy:outsource_attendance')

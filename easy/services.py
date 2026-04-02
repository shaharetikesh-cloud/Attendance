import calendar
from datetime import date
from decimal import Decimal

from .models import (
    AdvanceShiftChart,
    Employee,
    OperatorAttendanceSheet,
    OperatorLogicConfig,
    SubstationLogicAssignment,
    format_cpf_label,
    format_display_name,
    is_probable_vacant_name,
)

ATTENDANCE_BLANK = '-'
ATTENDANCE_PRESENT = 'P'
ATTENDANCE_OFF = 'off'
SHIFT_GENERAL = 'G'
SHIFT_OFF = 'off'
SHIFT_SEQUENCE = ['I', 'II', 'III']
OPERATOR_ROTATION = ['off', 'II', 'III', 'I', 'II', 'III', 'I']
DEFAULT_NIGHT_ALLOWANCE_RATE = Decimal('190.00')
NIGHT_ALLOWANCE_ROW_LIMIT = 4
DEFAULT_ATTENDANCE_CODES = (
    {'code': 'P', 'label': 'P', 'remark_label': 'P', 'remarkable': False},
    {'code': 'A', 'label': 'A', 'remark_label': 'A', 'remarkable': True},
    {'code': 'CL', 'label': 'CL', 'remark_label': 'CL', 'remarkable': True},
    {'code': 'EL', 'label': 'EL', 'remark_label': 'EL', 'remarkable': True},
    {'code': 'Medical', 'label': 'Medical', 'remark_label': 'Medical leave', 'remarkable': True},
    {'code': 'M', 'label': 'M', 'remark_label': 'Medical leave', 'remarkable': True},
    {'code': 'HCL', 'label': 'HCL', 'remark_label': 'HCL', 'remarkable': True},
    {'code': 'OD', 'label': 'OD', 'remark_label': 'OD', 'remarkable': True},
    {'code': 'LWP', 'label': 'LWP', 'remark_label': 'LWP', 'remarkable': True},
    {'code': 'C-OFF', 'label': 'C-OFF', 'remark_label': 'C-OFF', 'remarkable': True},
    {'code': 'off', 'label': 'off', 'remark_label': 'off', 'remarkable': False},
)




def get_operator_logic_config(substation):
    assignment = getattr(substation, 'logic_assignment', None)
    if assignment and assignment.config_id:
        return assignment.config
    return OperatorLogicConfig.objects.filter(is_active=True).order_by('id').first()


def get_rotation_pattern(substation):
    config = get_operator_logic_config(substation)
    return config.get_rotation_list() if config else OPERATOR_ROTATION


def get_night_allowance_rate(substation):
    config = get_operator_logic_config(substation)
    return config.night_allowance_rate if config else DEFAULT_NIGHT_ALLOWANCE_RATE


def get_max_operator_count(substation):
    config = get_operator_logic_config(substation)
    return config.max_operator_count if config else 4


def is_general_duty_enabled(substation):
    config = get_operator_logic_config(substation)
    return config.general_duty_enabled if config else True


def get_general_duty_fallback_shift(substation):
    config = get_operator_logic_config(substation)
    return config.general_duty_fallback_shift if config else SHIFT_GENERAL

def coerce_decimal(value):
    if value in (None, ''):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_attendance_code_definitions(extra_codes=None):
    definitions = [dict(item) for item in DEFAULT_ATTENDANCE_CODES]
    definition_by_code = {item['code']: item for item in definitions}

    for extra_code in extra_codes or []:
        code = extra_code.get('code')
        if not code:
            continue
        merged_definition = {
            'label': code,
            'remark_label': code,
            'remarkable': True,
            **extra_code,
        }
        if code in definition_by_code:
            definition_by_code[code].update(merged_definition)
        else:
            definition_by_code[code] = merged_definition
            definitions.append(definition_by_code[code])

    return definitions


def get_attendance_choices(extra_codes=None, include_blank=False):
    choices = [(item['code'], item.get('label', item['code'])) for item in get_attendance_code_definitions(extra_codes)]
    if include_blank:
        return [(ATTENDANCE_BLANK, ATTENDANCE_BLANK)] + choices
    return choices


def get_attendance_definition(code, extra_codes=None):
    if code == ATTENDANCE_BLANK:
        return {'code': ATTENDANCE_BLANK, 'label': ATTENDANCE_BLANK, 'remark_label': 'Blank', 'remarkable': False}
    if not code:
        return None
    for definition in get_attendance_code_definitions(extra_codes):
        if definition['code'] == code:
            return definition
    return None


def normalize_attendance_value(value, default_value=ATTENDANCE_PRESENT, extra_codes=None, allow_blank=False):
    if allow_blank and value in (None, ATTENDANCE_BLANK):
        return ATTENDANCE_BLANK
    if get_attendance_definition(value, extra_codes):
        return value
    return default_value


def should_generate_leave_remark(code, extra_codes=None):
    definition = get_attendance_definition(code, extra_codes)
    return bool(definition and definition.get('remarkable'))


def format_leave_label(code, extra_codes=None):
    definition = get_attendance_definition(code, extra_codes)
    if not definition:
        return code
    return definition.get('remark_label') or definition.get('label') or code


def _remark_day_text(total_days):
    return '1 day' if total_days == 1 else f'{total_days} days'


def group_leave_ranges(attendance_entries, day_headers, extra_codes=None):
    grouped_ranges = []

    for entry in attendance_entries:
        attendance_days = entry.get('attendance_days', {})
        employee_name = entry.get('display_name') or format_display_name(entry.get('employee_name', ''))
        current_range = None

        for day in day_headers:
            day_date = day['date']
            day_key = str(day['day'])
            attendance_value = normalize_attendance_value(attendance_days.get(day_key), ATTENDANCE_PRESENT, extra_codes)

            if should_generate_leave_remark(attendance_value, extra_codes):
                if (
                    current_range
                    and current_range['leave_code'] == attendance_value
                    and (day_date - current_range['end_date']).days == 1
                ):
                    current_range['end_date'] = day_date
                    current_range['days'] += 1
                else:
                    if current_range:
                        grouped_ranges.append(current_range)
                    current_range = {
                        'employee_name': employee_name,
                        'leave_code': attendance_value,
                        'leave_label': format_leave_label(attendance_value, extra_codes),
                        'start_date': day_date,
                        'end_date': day_date,
                        'days': 1,
                    }
            elif current_range:
                grouped_ranges.append(current_range)
                current_range = None

        if current_range:
            grouped_ranges.append(current_range)

    return grouped_ranges


def generate_leave_remarks(attendance_entries, day_headers, extra_codes=None):
    remarks = []
    for leave_range in group_leave_ranges(attendance_entries, day_headers, extra_codes):
        remarks.append(
            (
                f"{leave_range['employee_name']} availed {leave_range['leave_label']} "
                f"from {leave_range['start_date']:%d-%m-%Y} to {leave_range['end_date']:%d-%m-%Y} "
                f"for {_remark_day_text(leave_range['days'])}."
            )
        )
    return remarks


def build_report_remark_lines(auto_leave_remarks, manual_remark=''):
    lines = list(auto_leave_remarks or [])
    manual_lines = [line.strip() for line in str(manual_remark or '').splitlines() if line.strip()]
    lines.extend(manual_lines)
    return lines or ['-']


def format_decimal_for_input(value):
    if value in (None, ''):
        return ''
    decimal_value = coerce_decimal(value)
    return f'{decimal_value:.2f}'


def calculate_night_allowance_amount(night_count, rate):
    if night_count in (None, '') or rate in (None, ''):
        return None
    return Decimal(int(night_count)) * coerce_decimal(rate)


def vacant_allowance_name(index):
    return 'Vacant' if index == 1 else f'Vacant{index}'


def _allowance_base_row(serial_no, display_name, employee_id=None, rate=None, night_count=None, amount=None, remark=''):
    calculated_amount = calculate_night_allowance_amount(night_count, rate) if amount is None else coerce_decimal(amount)
    return {
        'serial_no': serial_no,
        'employee_id': employee_id,
        'display_name': display_name,
        'night_count': night_count,
        'rate': coerce_decimal(rate),
        'amount': calculated_amount,
        'remark': remark or '',
        'night_count_input': '' if night_count is None else str(night_count),
        'rate_input': format_decimal_for_input(rate),
        'amount_input': format_decimal_for_input(calculated_amount),
    }


def build_night_allowance_rows(operator_rows, saved_entries=None, default_rate=DEFAULT_NIGHT_ALLOWANCE_RATE):
    operator_rows = list(operator_rows or [])
    saved_entries = list(saved_entries or [])
    saved_entries_by_serial = {entry.serial_no: entry for entry in saved_entries}

    default_rows = []
    vacant_index = 1
    for serial_no in range(1, NIGHT_ALLOWANCE_ROW_LIMIT + 1):
        source_row = operator_rows[serial_no - 1] if serial_no <= len(operator_rows) else None
        if source_row:
            default_rows.append(
                _allowance_base_row(
                    serial_no=serial_no,
                    employee_id=source_row.get('employee_id'),
                    display_name=source_row.get('employee_name') or source_row.get('display_name') or f'Employee {serial_no}',
                    rate=default_rate,
                )
            )
        else:
            default_rows.append(
                _allowance_base_row(
                    serial_no=serial_no,
                    display_name=vacant_allowance_name(vacant_index),
                )
            )
            vacant_index += 1

    if not saved_entries_by_serial:
        return default_rows

    merged_rows = []
    for default_row in default_rows:
        entry = saved_entries_by_serial.get(default_row['serial_no'])
        if not entry:
            merged_rows.append(default_row)
            continue

        merged_rows.append(
            _allowance_base_row(
                serial_no=default_row['serial_no'],
                employee_id=entry.employee_id,
                display_name=entry.display_name or default_row['display_name'],
                night_count=entry.night_count,
                rate=entry.rate,
                amount=entry.amount,
                remark=entry.remark,
            )
        )
    return merged_rows


def build_day_headers(year, month):
    total_days = calendar.monthrange(year, month)[1]
    headers = []
    for day_number in range(1, total_days + 1):
        current_date = date(year, month, day_number)
        headers.append(
            {
                'day': day_number,
                'day_label': f'{day_number:02d}',
                'weekday': current_date.strftime('%a'),
                'date': current_date,
            }
        )
    return headers


def month_year_label(year, month):
    return date(year, month, 1).strftime('%b %Y')


def build_employee_snapshot(employee):
    is_vacant = bool(getattr(employee, 'is_vacant', False) or is_probable_vacant_name(employee.employee_name))
    return {
        'employee_id': employee.pk,
        'employee_name': employee.employee_name,
        'display_name': format_display_name(employee.employee_name, is_vacant),
        'designation_short': employee.designation_short,
        'cpf_no': employee.cpf_no,
        'cpf_display': employee.cpf_label,
        'working_place': getattr(employee, 'working_place', '') or '',
        'joining_date': getattr(employee, 'joining_date', None),
        'weekly_off_day': employee.weekly_off_day,
        'is_general_duty_operator': employee.is_general_duty_operator,
        'is_vacant': is_vacant,
        'employee_type': employee.employee_type,
    }


def normalize_day_map(day_map, day_headers, default_value=''):
    return {str(day['day']): day_map.get(str(day['day']), default_value) for day in day_headers}


def is_pre_joining_day(employee, current_date):
    joining_date = getattr(employee, 'joining_date', None)
    return bool(joining_date and current_date < joining_date)


def simple_attendance_for_date(employee, current_date):
    if is_pre_joining_day(employee, current_date):
        return ATTENDANCE_BLANK
    return ATTENDANCE_OFF if current_date.weekday() == int(employee.weekly_off_day) else ATTENDANCE_PRESENT

def attendance_for_shift(shift_value):
    return ATTENDANCE_OFF if shift_value == SHIFT_OFF else ATTENDANCE_PRESENT


def build_operator_attendance_map(shift_days, is_vacant=False, pre_joining_keys=None):
    pre_joining_keys = set(pre_joining_keys or [])
    if is_vacant:
        return {day_key: ATTENDANCE_BLANK for day_key in shift_days}
    values = {}
    for day_key, shift_value in shift_days.items():
        if day_key in pre_joining_keys:
            values[day_key] = ATTENDANCE_BLANK
        else:
            values[day_key] = attendance_for_shift(shift_value)
    return values


def normal_shift_for_date(current_date, weekly_off_day, rotation_pattern=None):
    rotation_pattern = rotation_pattern or OPERATOR_ROTATION
    offset = (current_date.weekday() - int(weekly_off_day)) % len(rotation_pattern)
    return rotation_pattern[offset]


def previous_month(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def get_previous_shift_sources(substation, year, month):
    previous_year, previous_month_value = previous_month(year, month)
    for model in (AdvanceShiftChart, OperatorAttendanceSheet):
        sheet = model.objects.filter(
            substation=substation,
            year=previous_year,
            month=previous_month_value,
        ).order_by('-updated_at').first()
        if sheet:
            return {
                row.employee_id: [row.shift_days.get(str(day), SHIFT_OFF) for day in range(1, calendar.monthrange(previous_year, previous_month_value)[1] + 1)]
                for row in sheet.rows.all()
                if row.employee_id
            }
    return {}


def infer_seed_index(shift_values, rotation_pattern=None):
    rotation_pattern = rotation_pattern or OPERATOR_ROTATION
    last_window = shift_values[-len(rotation_pattern):]
    if SHIFT_OFF not in last_window:
        return None
    last_off_index = max(index for index, value in enumerate(last_window) if value == SHIFT_OFF)
    suffix = last_window[last_off_index:]
    if suffix == rotation_pattern[: len(suffix)]:
        return len(suffix) % len(rotation_pattern)
    return None


def build_normal_operator_shift_map(employee, day_headers, previous_sources=None, rotation_pattern=None):
    previous_sources = previous_sources or {}
    rotation_pattern = rotation_pattern or OPERATOR_ROTATION
    previous_shift_values = previous_sources.get(employee.pk, [])
    seed_index = infer_seed_index(previous_shift_values, rotation_pattern)
    shift_map = {}

    for position, day in enumerate(day_headers):
        if seed_index is not None:
            shift_value = rotation_pattern[(seed_index + position) % len(rotation_pattern)]
        else:
            shift_value = normal_shift_for_date(day['date'], employee.weekly_off_day, rotation_pattern)
        shift_map[str(day['day'])] = shift_value
    return shift_map


def warnings_for_operator_setup(employees, max_operator_count=4, general_duty_enabled=True):
    warnings = []
    operators = [employee for employee in employees if employee.employee_type == Employee.EmployeeType.OPERATOR]
    general_duty = [employee for employee in operators if employee.is_general_duty_operator]
    normal_operators = [employee for employee in operators if not employee.is_general_duty_operator]

    if len(operators) > max_operator_count:
        warnings.append(f'Soft rule: keep maximum {max_operator_count} operators per substation.')
    if general_duty_enabled and len(general_duty) == 0:
        warnings.append('No general duty operator is marked. General duty coverage will not be auto-filled.')
    if len(general_duty) > 1:
        warnings.append('More than one general duty operator is marked. Please keep only one.')
    if len(normal_operators) != 3:
        warnings.append('Best results come with 3 shift operators and 1 general duty operator.')
    return warnings


def generate_operator_chart(substation, year, month, use_previous_pattern=True):
    day_headers = build_day_headers(year, month)
    employees = list(
        Employee.objects.filter(substation=substation, employee_type=Employee.EmployeeType.OPERATOR).order_by('id')
    )
    previous_sources = get_previous_shift_sources(substation, year, month) if use_previous_pattern else {}
    rotation_pattern = get_rotation_pattern(substation)
    general_duty_enabled = is_general_duty_enabled(substation)
    general_duty_fallback_shift = get_general_duty_fallback_shift(substation)
    warnings = warnings_for_operator_setup(employees, get_max_operator_count(substation), general_duty_enabled)

    normal_shift_maps = {}
    general_duty_employee = None
    for employee in employees:
        if general_duty_enabled and employee.is_general_duty_operator and general_duty_employee is None:
            general_duty_employee = employee
            continue
        normal_shift_maps[employee.pk] = build_normal_operator_shift_map(employee, day_headers, previous_sources, rotation_pattern)

    rows = []
    for employee in employees:
        snapshot = build_employee_snapshot(employee)
        is_vacant = snapshot['is_vacant']
        if general_duty_enabled and employee.is_general_duty_operator:
            shift_days = {}
            for day in day_headers:
                day_key = str(day['day'])
                if day['date'].weekday() == int(employee.weekly_off_day):
                    shift_value = SHIFT_OFF
                else:
                    occupied = {shift_map[day_key] for shift_map in normal_shift_maps.values()}
                    missing_shift = next((shift for shift in SHIFT_SEQUENCE if shift not in occupied), None)
                    shift_value = missing_shift if missing_shift else general_duty_fallback_shift
                shift_days[day_key] = shift_value
        else:
            shift_days = normal_shift_maps.get(employee.pk, {})

        pre_joining_keys = {str(day['day']) for day in day_headers if is_pre_joining_day(employee, day['date'])}
        attendance_days = build_operator_attendance_map(shift_days, is_vacant=is_vacant, pre_joining_keys=pre_joining_keys)
        rows.append(
            {
                **snapshot,
                'attendance_days': normalize_day_map(
                    attendance_days,
                    day_headers,
                    ATTENDANCE_BLANK if is_vacant else ATTENDANCE_OFF,
                ),
                'shift_days': normalize_day_map(shift_days, day_headers, SHIFT_OFF),
            }
        )

    return {
        'days': day_headers,
        'rows': rows,
        'warnings': warnings,
        'leave_remarks': generate_leave_remarks(rows, day_headers),
    }


def generate_advance_shift_chart(substation, year, month):
    operator_chart = generate_operator_chart(substation, year, month, use_previous_pattern=True)
    rows = []
    for row in operator_chart['rows']:
        rows.append(
            {
                key: value
                for key, value in row.items()
                if key not in {'attendance_days'}
            }
        )
    return {'days': operator_chart['days'], 'rows': rows, 'warnings': operator_chart['warnings']}


def generate_simple_attendance(substation, year, month, employee_type, empty_warning):
    day_headers = build_day_headers(year, month)
    employees = list(
        Employee.objects.filter(substation=substation, employee_type=employee_type).order_by('id')
    )
    rows = []
    for employee in employees:
        attendance_days = {}
        for day in day_headers:
            attendance_days[str(day['day'])] = simple_attendance_for_date(employee, day['date'])
        rows.append(
            {
                **build_employee_snapshot(employee),
                'attendance_days': normalize_day_map(attendance_days, day_headers, ATTENDANCE_OFF),
            }
        )

    warnings = []
    if not rows:
        warnings.append(empty_warning)
    return {
        'days': day_headers,
        'rows': rows,
        'warnings': warnings,
        'leave_remarks': generate_leave_remarks(rows, day_headers),
    }


def generate_tech_attendance(substation, year, month):
    return generate_simple_attendance(
        substation,
        year,
        month,
        Employee.EmployeeType.TECH_ENGINEER,
        'No tech or engineer employees are configured for this substation.',
    )


def generate_apprentice_attendance(substation, year, month):
    return generate_simple_attendance(
        substation,
        year,
        month,
        Employee.EmployeeType.APPRENTICE,
        'No apprentice employees are configured for this substation.',
    )


def generate_outsource_attendance(substation, year, month):
    return generate_simple_attendance(
        substation,
        year,
        month,
        Employee.EmployeeType.OUTSOURCE,
        'No outsource employees are configured for this substation.',
    )


def generate_other_attendance(substation, year, month):
    return generate_simple_attendance(
        substation,
        year,
        month,
        Employee.EmployeeType.OTHER,
        'No other group employees are configured for this substation.',
    )


def load_operator_sheet_rows(sheet):
    day_headers = build_day_headers(sheet.year, sheet.month)
    rows = []
    for row in sheet.rows.all():
        row_is_vacant = bool(
            getattr(row, 'is_vacant', False)
            or getattr(row.employee, 'is_vacant', False)
            or is_probable_vacant_name(row.employee_name)
        )
        rows.append(
            {
                'employee_id': row.employee_id,
                'employee_name': row.employee_name,
                'display_name': format_display_name(row.employee_name, row_is_vacant),
                'designation_short': row.designation_short,
                'cpf_no': row.cpf_no,
                'cpf_display': format_cpf_label(row.cpf_no),
                'working_place': getattr(row, 'working_place', '') or '',
                'is_vacant': row_is_vacant,
                'attendance_days': normalize_day_map(
                    row.attendance_days,
                    day_headers,
                    ATTENDANCE_BLANK if row_is_vacant else ATTENDANCE_OFF,
                ),
                'shift_days': normalize_day_map(row.shift_days, day_headers, SHIFT_OFF),
            }
        )
    return {
        'days': day_headers,
        'rows': rows,
        'night_allowance_rows': build_night_allowance_rows(rows, sheet.night_allowance_entries.all()),
        'leave_remarks': generate_leave_remarks(rows, day_headers),
    }


def load_advance_sheet_rows(sheet):
    day_headers = build_day_headers(sheet.year, sheet.month)
    rows = []
    for row in sheet.rows.all():
        rows.append(
            {
                'employee_id': row.employee_id,
                'employee_name': row.employee_name,
                'display_name': format_display_name(row.employee_name),
                'designation_short': row.designation_short,
                'cpf_no': row.cpf_no,
                'cpf_display': format_cpf_label(row.cpf_no),
                'working_place': getattr(row, 'working_place', '') or '',
                'shift_days': normalize_day_map(row.shift_days, day_headers, SHIFT_OFF),
            }
        )
    return {'days': day_headers, 'rows': rows}


def load_simple_sheet_rows(sheet):
    day_headers = build_day_headers(sheet.year, sheet.month)
    rows = []
    for row in sheet.rows.all():
        rows.append(
            {
                'employee_id': row.employee_id,
                'employee_name': row.employee_name,
                'display_name': format_display_name(row.employee_name),
                'designation_short': row.designation_short,
                'cpf_no': row.cpf_no,
                'cpf_display': format_cpf_label(row.cpf_no),
                'working_place': getattr(row, 'working_place', '') or '',
                'attendance_days': normalize_day_map(row.attendance_days, day_headers, ATTENDANCE_OFF),
            }
        )
    return {
        'days': day_headers,
        'rows': rows,
        'leave_remarks': generate_leave_remarks(rows, day_headers),
    }


def load_tech_sheet_rows(sheet):
    return load_simple_sheet_rows(sheet)


def load_apprentice_sheet_rows(sheet):
    return load_simple_sheet_rows(sheet)


def load_outsource_sheet_rows(sheet):
    return load_simple_sheet_rows(sheet)

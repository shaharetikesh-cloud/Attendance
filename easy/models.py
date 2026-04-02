import re
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


VACANT_NAME_PATTERN = re.compile(r'^vacant(?:\d+)?$', re.IGNORECASE)


def is_probable_vacant_name(name):
    clean_name = (name or '').strip()
    return bool(clean_name and VACANT_NAME_PATTERN.fullmatch(clean_name))


def format_display_name(name, is_vacant=False):
    clean_name = (name or '').strip()
    if not clean_name:
        return 'Employee'
    if is_vacant or is_probable_vacant_name(clean_name):
        return clean_name
    if clean_name.lower().startswith('shri'):
        return clean_name
    return f'Shri. {clean_name}'


def format_cpf_label(cpf_no):
    return f'CPF- {cpf_no}' if cpf_no else 'CPF- --'


class EmployeeDisplayMixin:
    @property
    def display_name(self):
        return format_display_name(self.employee_name, getattr(self, 'is_vacant', False))

    @property
    def cpf_label(self):
        return format_cpf_label(self.cpf_no)

    @property
    def display_name_with_cpf(self):
        return f'{self.display_name}\n{self.cpf_label}'


class Substation(models.Model):
    substation_name = models.CharField(max_length=200)
    om_name = models.CharField(max_length=200, verbose_name='O&M Name')
    sub_division_name = models.CharField(max_length=200)
    remark = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['substation_name']

    def __str__(self):
        return f'{self.substation_name} | {self.om_name} | {self.sub_division_name}'


class Employee(EmployeeDisplayMixin, models.Model):
    class EmployeeType(models.TextChoices):
        OPERATOR = 'operator', 'Operator'
        TECH_ENGINEER = 'tech_engineer', 'Technician / Engineer'
        APPRENTICE = 'apprentice', 'Apprentice'
        OUTSOURCE = 'outsource', 'Outsource'
        OTHER = 'other', 'Other'

    class WeekOffDay(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    OPERATOR_DESIGNATIONS = ('Opt', 'Sr Opt', 'Pre. Opt', 'O/S Opt', 'Up Saha')
    TECHNICIAN_DESIGNATIONS = ('Tech', 'Sr.Tech', 'Pre.Tech', 'Vidyu Saha')
    ENGINEER_DESIGNATIONS = ('GTE', 'AE', 'JE')
    TECHNICIAN_ENGINEER_DESIGNATIONS = TECHNICIAN_DESIGNATIONS + ENGINEER_DESIGNATIONS
    APPRENTICE_DESIGNATIONS = ('App',)
    OUTSOURCE_DESIGNATIONS = ('Tec', 'Opt-Out')
    OTHER_DESIGNATIONS = ('Other',)

    substation = models.ForeignKey(Substation, on_delete=models.CASCADE, related_name='employees')
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    weekly_off_day = models.PositiveSmallIntegerField(choices=WeekOffDay.choices)
    is_general_duty_operator = models.BooleanField(default=False)
    is_vacant = models.BooleanField(default=False)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['substation__substation_name', 'id']

    @classmethod
    def designation_choices_for(cls, employee_type):
        designation_groups = {
            cls.EmployeeType.OPERATOR: cls.OPERATOR_DESIGNATIONS,
            cls.EmployeeType.TECH_ENGINEER: cls.TECHNICIAN_ENGINEER_DESIGNATIONS,
            cls.EmployeeType.APPRENTICE: cls.APPRENTICE_DESIGNATIONS,
            cls.EmployeeType.OUTSOURCE: cls.OUTSOURCE_DESIGNATIONS,
            cls.EmployeeType.OTHER: cls.OTHER_DESIGNATIONS,
        }
        return [(value, value) for value in designation_groups.get(employee_type, cls.OPERATOR_DESIGNATIONS)]

    @classmethod
    def valid_designations_for(cls, employee_type):
        return {value for value, _label in cls.designation_choices_for(employee_type)}

    @classmethod
    def designation_error_message(cls, employee_type):
        error_messages = {
            cls.EmployeeType.OPERATOR: 'Operator designation must be one of: Opt, Sr Opt, Pre. Opt, O/S Opt, Up Saha.',
            cls.EmployeeType.TECH_ENGINEER: 'Tech / engineer designation must be one of: Tech, Sr.Tech, Pre.Tech, Vidyu Saha, GTE, AE, JE.',
            cls.EmployeeType.APPRENTICE: 'Apprentice designation must be: App.',
            cls.EmployeeType.OUTSOURCE: 'Outsource designation must be one of: Tec, Opt-Out.',
            cls.EmployeeType.OTHER: 'Other group designation must be: Other.',
        }
        return error_messages.get(employee_type, 'Invalid designation for the selected employee type.')

    def clean(self):
        errors = {}

        if self.designation_short not in self.valid_designations_for(self.employee_type):
            errors['designation_short'] = self.designation_error_message(self.employee_type)

        if self.employee_type != self.EmployeeType.OPERATOR and self.is_general_duty_operator:
            errors['is_general_duty_operator'] = 'General duty is only applicable for operator entries.'

        if self.substation_id and self.is_general_duty_operator:
            existing_general_duty = Employee.objects.filter(
                substation=self.substation,
                employee_type=self.EmployeeType.OPERATOR,
                is_general_duty_operator=True,
            )
            if self.pk:
                existing_general_duty = existing_general_duty.exclude(pk=self.pk)
            if existing_general_duty.exists():
                errors['is_general_duty_operator'] = 'Only one general duty operator can be marked for a substation.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.employee_name} ({self.get_employee_type_display()})'


class MonthlySheetBase(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    substation = models.ForeignKey(Substation, on_delete=models.CASCADE)
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    certificate_text = models.TextField(blank=True)
    remark = models.TextField(blank=True)
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='%(class)s_submitted_sheets')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='%(class)s_approved_sheets')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-year', '-month', 'substation__substation_name']

    @property
    def month_year_label(self):
        return date(self.year, self.month, 1).strftime('%b %Y')

    def __str__(self):
        return f'{self.substation.substation_name} - {self.month_year_label}'


class OperatorAttendanceSheet(MonthlySheetBase):
    night_shift_allowance_units = models.PositiveIntegerField(default=0)
    night_shift_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('190.00'))

    class Meta(MonthlySheetBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['substation', 'month', 'year'], name='unique_operator_sheet_per_month'),
        ]

    def sync_night_allowance_summary(self):
        entries = list(self.night_allowance_entries.all())
        if not entries:
            return
        self.night_shift_allowance_units = sum(entry.night_count or 0 for entry in entries)
        first_rate = next((entry.rate for entry in entries if entry.rate is not None), Decimal('0.00'))
        self.night_shift_rate = first_rate or Decimal('0.00')

    @property
    def allowance_amount(self):
        entries = list(self.night_allowance_entries.all())
        if entries:
            return sum(((entry.amount or Decimal('0.00')) for entry in entries), Decimal('0.00'))
        return Decimal(self.night_shift_allowance_units) * self.night_shift_rate


class OperatorAttendanceRow(EmployeeDisplayMixin, models.Model):
    sheet = models.ForeignKey(OperatorAttendanceSheet, on_delete=models.CASCADE, related_name='rows')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    is_vacant = models.BooleanField(default=False)
    attendance_days = models.JSONField(default=dict, blank=True)
    shift_days = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.employee_name} - {self.sheet}'


class EasyNightAllowanceEntry(models.Model):
    operator_month = models.ForeignKey(
        OperatorAttendanceSheet,
        on_delete=models.CASCADE,
        related_name='night_allowance_entries',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='night_allowance_entries',
    )
    display_name = models.CharField(max_length=200)
    serial_no = models.PositiveSmallIntegerField()
    night_count = models.PositiveIntegerField(null=True, blank=True)
    rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    remark = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['serial_no', 'id']
        constraints = [
            models.UniqueConstraint(fields=['operator_month', 'serial_no'], name='unique_night_allowance_row_per_sheet'),
        ]

    def clean(self):
        errors = {}
        if not self.display_name and not self.employee_id:
            errors['display_name'] = 'Display name is required for employee-wise night allowance rows.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.employee_id and not self.display_name:
            self.display_name = self.employee.employee_name

        if self.night_count is None or self.rate is None:
            self.amount = None
        else:
            self.amount = Decimal(self.night_count) * Decimal(str(self.rate))

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.display_name} - {self.operator_month}'


class AdvanceShiftChart(MonthlySheetBase):
    class Meta(MonthlySheetBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['substation', 'month', 'year'], name='unique_advance_sheet_per_month'),
        ]


class AdvanceShiftRow(EmployeeDisplayMixin, models.Model):
    sheet = models.ForeignKey(AdvanceShiftChart, on_delete=models.CASCADE, related_name='rows')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    shift_days = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.employee_name} - {self.sheet}'


class TechAttendanceSheet(MonthlySheetBase):
    class Meta(MonthlySheetBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['substation', 'month', 'year'], name='unique_tech_sheet_per_month'),
        ]


class TechAttendanceRow(EmployeeDisplayMixin, models.Model):
    sheet = models.ForeignKey(TechAttendanceSheet, on_delete=models.CASCADE, related_name='rows')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    attendance_days = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.employee_name} - {self.sheet}'


class ApprenticeAttendanceSheet(MonthlySheetBase):
    class Meta(MonthlySheetBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['substation', 'month', 'year'], name='unique_apprentice_sheet_per_month'),
        ]


class ApprenticeAttendanceRow(EmployeeDisplayMixin, models.Model):
    sheet = models.ForeignKey(ApprenticeAttendanceSheet, on_delete=models.CASCADE, related_name='rows')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    attendance_days = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.employee_name} - {self.sheet}'


class OutsourceAttendanceSheet(MonthlySheetBase):
    class Meta(MonthlySheetBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['substation', 'month', 'year'], name='unique_outsource_sheet_per_month'),
        ]


class OutsourceAttendanceRow(EmployeeDisplayMixin, models.Model):
    sheet = models.ForeignKey(OutsourceAttendanceSheet, on_delete=models.CASCADE, related_name='rows')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    employee_name = models.CharField(max_length=200)
    designation_short = models.CharField(max_length=40)
    cpf_no = models.CharField(max_length=50, blank=True)
    working_place = models.CharField(max_length=200, blank=True)
    attendance_days = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.employee_name} - {self.sheet}'


class AppSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key

    @classmethod
    def get_value(cls, key, default=''):
        setting = cls.objects.filter(key=key).first()
        return setting.value if setting else default

    @classmethod
    def get_bool(cls, key, default=False):
        value = str(cls.get_value(key, 'true' if default else 'false')).strip().lower()
        return value in {'1', 'true', 'yes', 'on'}

    @classmethod
    def set_value(cls, key, value):
        obj, _ = cls.objects.update_or_create(key=key, defaults={'value': str(value)})
        return obj


class OperatorLogicConfig(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    max_operator_count = models.PositiveSmallIntegerField(default=4)
    rotation_pattern = models.CharField(max_length=200, default='off,II,III,I,II,III,I')
    general_duty_enabled = models.BooleanField(default=True)
    general_duty_fallback_shift = models.CharField(max_length=20, default='G')
    night_allowance_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('190.00'))
    allow_vacant_rows = models.BooleanField(default=True)
    remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_rotation_list(self):
        values = [item.strip() for item in (self.rotation_pattern or '').split(',') if item.strip()]
        return values or ['off', 'II', 'III', 'I', 'II', 'III', 'I']


class SubstationLogicAssignment(models.Model):
    substation = models.OneToOneField(Substation, on_delete=models.CASCADE, related_name='logic_assignment')
    config = models.ForeignKey(OperatorLogicConfig, on_delete=models.PROTECT, related_name='assigned_substations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['substation__substation_name']

    def __str__(self):
        return f'{self.substation.substation_name} -> {self.config.name}'

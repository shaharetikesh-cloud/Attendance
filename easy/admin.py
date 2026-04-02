from django.contrib import admin

from .models import (
    AdvanceShiftChart,
    AppSetting,
    ApprenticeAttendanceSheet,
    Employee,
    OperatorAttendanceSheet,
    OperatorLogicConfig,
    OutsourceAttendanceSheet,
    Substation,
    SubstationLogicAssignment,
    TechAttendanceSheet,
)


@admin.register(Substation)
class SubstationAdmin(admin.ModelAdmin):
    list_display = ('substation_name', 'om_name', 'sub_division_name', 'is_active')
    list_filter = ('is_active', 'om_name')
    search_fields = ('substation_name', 'om_name', 'sub_division_name')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'substation', 'employee_type', 'designation_short', 'cpf_no', 'is_general_duty_operator', 'is_vacant')
    list_filter = ('employee_type', 'is_general_duty_operator', 'is_vacant', 'substation')
    search_fields = ('employee_name', 'cpf_no', 'working_place')


@admin.register(OperatorAttendanceSheet)
class OperatorAttendanceSheetAdmin(admin.ModelAdmin):
    list_display = ('substation', 'month', 'year', 'approval_status', 'updated_at')
    list_filter = ('approval_status', 'year', 'month', 'substation')
    search_fields = ('substation__substation_name',)


@admin.register(AdvanceShiftChart)
class AdvanceShiftChartAdmin(admin.ModelAdmin):
    list_display = ('substation', 'month', 'year', 'approval_status', 'updated_at')
    list_filter = ('approval_status', 'year', 'month')


@admin.register(TechAttendanceSheet)
class TechAttendanceSheetAdmin(admin.ModelAdmin):
    list_display = ('substation', 'month', 'year', 'approval_status', 'updated_at')
    list_filter = ('approval_status', 'year', 'month')


@admin.register(ApprenticeAttendanceSheet)
class ApprenticeAttendanceSheetAdmin(admin.ModelAdmin):
    list_display = ('substation', 'month', 'year', 'approval_status', 'updated_at')
    list_filter = ('approval_status', 'year', 'month')


@admin.register(OutsourceAttendanceSheet)
class OutsourceAttendanceSheetAdmin(admin.ModelAdmin):
    list_display = ('substation', 'month', 'year', 'approval_status', 'updated_at')
    list_filter = ('approval_status', 'year', 'month')


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'updated_at')
    search_fields = ('key', 'value')


@admin.register(OperatorLogicConfig)
class OperatorLogicConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'max_operator_count', 'general_duty_enabled', 'night_allowance_rate', 'is_active')
    list_filter = ('is_active', 'general_duty_enabled')


@admin.register(SubstationLogicAssignment)
class SubstationLogicAssignmentAdmin(admin.ModelAdmin):
    list_display = ('substation', 'config', 'updated_at')
    list_filter = ('config',)

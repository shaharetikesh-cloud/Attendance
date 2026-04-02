import calendar
import json
from datetime import date

from django import forms

from core.permissions import get_allowed_substations

from .models import Employee, Substation

DEFAULT_OPERATOR_CERTIFICATE = 'The all employees are wearing their clean uniform and using their own vehicle at work.'
DEFAULT_STAFF_CERTIFICATE = 'This is to certify that the above all employees are staying at headquarters.'


def month_choices():
    return [(number, calendar.month_name[number]) for number in range(1, 13)]


class SubstationForm(forms.ModelForm):
    class Meta:
        model = Substation
        fields = ['substation_name', 'om_name', 'sub_division_name', 'remark', 'is_active']
        widgets = {
            'remark': forms.Textarea(attrs={'rows': 3}),
            'is_active': forms.CheckboxInput(),
        }


class EmployeeForm(forms.ModelForm):
    designation_short = forms.ChoiceField(choices=())

    class Meta:
        model = Employee
        fields = [
            'substation',
            'employee_name',
            'employee_type',
            'designation_short',
            'cpf_no',
            'joining_date',
            'working_place',
            'weekly_off_day',
            'is_general_duty_operator',
            'is_vacant',
        ]
        widgets = {
            'substation': forms.HiddenInput(),
            'is_general_duty_operator': forms.CheckboxInput(),
            'is_vacant': forms.CheckboxInput(),
        }
        help_texts = {
            'designation_short': 'Designation choices load automatically for operator, technician / engineer, apprentice, and outsource staff.',
            'cpf_no': 'Optional field.',
            'joining_date': 'Optional. If filled, days before joining date can stay blank (-) in the attendance month.',
            'working_place': 'Optional. Useful for outsource or staff working at multiple places.',
            'is_general_duty_operator': 'Applicable only for operator entries.',
            'is_vacant': 'Use this for Vacant, Vacant1, Vacant2, or Vacant3 planning rows so operator attendance stays blank by default.',
        }

    def __init__(self, *args, selected_substation=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['substation'].queryset = get_allowed_substations(user) if user else Substation.objects.all()
        if selected_substation:
            self.fields['substation'].initial = selected_substation.pk

        employee_type_value = (
            self.data.get(self.add_prefix('employee_type'))
            if self.is_bound
            else self.initial.get('employee_type') or getattr(self.instance, 'employee_type', None)
        )
        if not employee_type_value:
            employee_type_value = Employee.EmployeeType.OPERATOR

        designation_value = (
            self.data.get(self.add_prefix('designation_short'))
            if self.is_bound
            else self.initial.get('designation_short') or getattr(self.instance, 'designation_short', '')
        )

        operator_choices = Employee.designation_choices_for(Employee.EmployeeType.OPERATOR)
        tech_engineer_choices = Employee.designation_choices_for(Employee.EmployeeType.TECH_ENGINEER)
        apprentice_choices = Employee.designation_choices_for(Employee.EmployeeType.APPRENTICE)
        outsource_choices = Employee.designation_choices_for(Employee.EmployeeType.OUTSOURCE)
        other_choices = Employee.designation_choices_for(Employee.EmployeeType.OTHER)
        available_choices = Employee.designation_choices_for(employee_type_value)
        available_values = {value for value, _label in available_choices}

        self.fields['designation_short'].choices = [('', 'Select designation')] + available_choices
        self.fields['designation_short'].initial = designation_value if designation_value in available_values else ''

        self.fields['designation_short'].widget.attrs.update(
            {
                'data-placeholder': 'Select designation',
                'data-operator-choices': json.dumps(operator_choices),
                'data-tech-engineer-choices': json.dumps(tech_engineer_choices),
                'data-apprentice-choices': json.dumps(apprentice_choices),
                'data-outsource-choices': json.dumps(outsource_choices),
                'data-other-choices': json.dumps(other_choices),
            }
        )


class BaseMonthlyForm(forms.Form):
    substation = forms.ModelChoiceField(queryset=Substation.objects.none())
    month = forms.ChoiceField(choices=month_choices())
    year = forms.IntegerField(min_value=2024, max_value=2100)
    remark = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        today = date.today()
        qs = get_allowed_substations(user) if user else Substation.objects.filter(is_active=True).order_by('substation_name')
        self.fields['substation'].queryset = qs.filter(is_active=True).order_by('substation_name')
        self.fields['month'].initial = today.month
        self.fields['year'].initial = today.year


class OperatorChartForm(BaseMonthlyForm):
    certificate_text = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), initial=DEFAULT_OPERATOR_CERTIFICATE)


class AdvanceShiftForm(BaseMonthlyForm):
    certificate_text = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), initial=DEFAULT_OPERATOR_CERTIFICATE)


class TechAttendanceForm(BaseMonthlyForm):
    certificate_text = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), initial=DEFAULT_STAFF_CERTIFICATE)


class ApprenticeAttendanceForm(BaseMonthlyForm):
    certificate_text = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), initial=DEFAULT_STAFF_CERTIFICATE)


class OutsourceAttendanceForm(BaseMonthlyForm):
    certificate_text = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}), initial=DEFAULT_STAFF_CERTIFICATE)

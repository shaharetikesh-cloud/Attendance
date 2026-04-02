from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import UserProfile, UserSubstationAccess
from easy.models import (
    AppSetting,
    Employee,
    OperatorAttendanceSheet,
    OperatorAttendanceRow,
    Substation,
)


class AttendanceSecurityAndSaveTests(TestCase):
    def setUp(self):
        self.substation = Substation.objects.create(
            substation_name='Test SS',
            om_name='OM',
            sub_division_name='SubDiv',
            is_active=True,
        )
        self.user = User.objects.create_user(username='entry1', password='pass12345', is_active=True)
        self.user.profile.role = UserProfile.ROLE_DATA_ENTRY
        self.user.profile.is_active = True
        self.user.profile.save()
        UserSubstationAccess.objects.create(user=self.user, substation=self.substation)
        self.client.login(username='entry1', password='pass12345')
        self.employee = Employee.objects.create(
            substation=self.substation,
            employee_name='Test Operator',
            designation_short='Opt',
            cpf_no='123',
            working_place='Yard',
            weekly_off_day=0,
            employee_type=Employee.EmployeeType.OPERATOR,
        )

    def test_operator_save_persists_working_place(self):
        AppSetting.set_value('approval_required', 'false')
        response = self.client.post(
            reverse('easy:operator_chart'),
            {
                'substation': self.substation.pk,
                'month': 4,
                'year': 2026,
                'remark': 'r',
                'certificate_text': 'c',
                'action': 'save',
                'row_total': 1,
                'row_0_employee_id': self.employee.pk,
                'row_0_employee_name': self.employee.employee_name,
                'row_0_designation_short': self.employee.designation_short,
                'row_0_cpf_no': self.employee.cpf_no,
                'row_0_working_place': 'Switch Yard',
                'row_0_is_vacant': '',
                'row_0_attendance_1': 'P',
                'row_0_shift_1': 'I',
                'night_allowance_total': 0,
            },
        )
        self.assertEqual(response.status_code, 302)
        row = OperatorAttendanceRow.objects.get()
        self.assertEqual(row.working_place, 'Switch Yard')

    def test_invalid_night_allowance_does_not_save_sheet(self):
        response = self.client.post(
            reverse('easy:operator_chart'),
            {
                'substation': self.substation.pk,
                'month': 4,
                'year': 2026,
                'remark': 'r',
                'certificate_text': 'c',
                'action': 'save',
                'row_total': 1,
                'row_0_employee_id': self.employee.pk,
                'row_0_employee_name': self.employee.employee_name,
                'row_0_designation_short': self.employee.designation_short,
                'row_0_cpf_no': self.employee.cpf_no,
                'row_0_working_place': 'Switch Yard',
                'row_0_is_vacant': '',
                'row_0_attendance_1': 'P',
                'row_0_shift_1': 'I',
                'night_allowance_total': 1,
                'night_0_display_name': 'Test Operator',
                'night_0_night_count': 'abc',
                'night_0_rate': '190',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OperatorAttendanceSheet.objects.exists())



    def test_viewer_cannot_save_operator_sheet(self):
        viewer = User.objects.create_user(username='viewer1', password='pass12345', is_active=True)
        viewer.profile.role = UserProfile.ROLE_VIEWER
        viewer.profile.is_active = True
        viewer.profile.save()
        UserSubstationAccess.objects.create(user=viewer, substation=self.substation)
        self.client.logout()
        self.client.login(username='viewer1', password='pass12345')

        response = self.client.post(
            reverse('easy:operator_chart'),
            {
                'substation': self.substation.pk,
                'month': 4,
                'year': 2026,
                'remark': 'r',
                'certificate_text': 'c',
                'action': 'save',
                'row_total': 1,
                'row_0_employee_id': self.employee.pk,
                'row_0_employee_name': self.employee.employee_name,
                'row_0_designation_short': self.employee.designation_short,
                'row_0_cpf_no': self.employee.cpf_no,
                'row_0_working_place': 'Switch Yard',
                'row_0_is_vacant': '',
                'row_0_attendance_1': 'P',
                'row_0_shift_1': 'I',
                'night_allowance_total': 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OperatorAttendanceSheet.objects.exists())
        messages = list(response.context['messages'])
        self.assertTrue(any('view-only access' in str(message) for message in messages))

    def test_data_entry_cannot_modify_approved_sheet(self):
        AppSetting.set_value('approval_required', 'true')
        sheet = OperatorAttendanceSheet.objects.create(
            substation=self.substation,
            month=4,
            year=2026,
            approval_status=OperatorAttendanceSheet.STATUS_APPROVED,
        )
        response = self.client.post(
            reverse('easy:operator_chart'),
            {
                'substation': self.substation.pk,
                'month': 4,
                'year': 2026,
                'remark': 'r',
                'certificate_text': 'c',
                'action': 'save',
                'row_total': 1,
                'row_0_employee_id': self.employee.pk,
                'row_0_employee_name': self.employee.employee_name,
                'row_0_designation_short': self.employee.designation_short,
                'row_0_cpf_no': self.employee.cpf_no,
                'row_0_working_place': 'New Place',
                'row_0_is_vacant': '',
                'row_0_attendance_1': 'P',
                'row_0_shift_1': 'I',
                'night_allowance_total': 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        sheet.refresh_from_db()
        self.assertEqual(sheet.approval_status, OperatorAttendanceSheet.STATUS_APPROVED)
        self.assertFalse(OperatorAttendanceRow.objects.exists())
        messages = list(response.context['messages'])
        self.assertTrue(any('locked' in str(message).lower() for message in messages))

    def test_pdf_requires_substation_access(self):
        other_substation = Substation.objects.create(
            substation_name='Other SS', om_name='OM', sub_division_name='SubDiv', is_active=True
        )
        sheet = OperatorAttendanceSheet.objects.create(substation=other_substation, month=4, year=2026)
        response = self.client.get(reverse('easy:operator_chart_pdf', args=[sheet.pk]))
        self.assertEqual(response.status_code, 403)

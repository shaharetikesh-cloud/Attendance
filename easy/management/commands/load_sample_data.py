from django.core.management.base import BaseCommand
from django.db import transaction

from easy.models import Employee, Substation


class Command(BaseCommand):
    help = 'Load sample substation and employee records for quick manual testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing sample substation records before reloading them.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        station_name = '33KV SUB-STATION Sample Yeldari'

        if options['replace']:
            Substation.objects.filter(substation_name=station_name).delete()

        substation, created = Substation.objects.get_or_create(
            substation_name=station_name,
            defaults={
                'om_name': 'O&M Selu',
                'sub_division_name': 'O&M Jintur',
                'remark': 'Sample data for MSEDCL Easy Attendance testing',
                'is_active': True,
            },
        )

        employees = [
            {
                'employee_name': 'Tikaram P Shahare',
                'designation_short': 'Opt',
                'cpf_no': '2847876',
                'weekly_off_day': Employee.WeekOffDay.SUNDAY,
                'is_general_duty_operator': False,
                'employee_type': Employee.EmployeeType.OPERATOR,
            },
            {
                'employee_name': 'G.B. Hanvate',
                'designation_short': 'Sr Opt',
                'cpf_no': '',
                'weekly_off_day': Employee.WeekOffDay.MONDAY,
                'is_general_duty_operator': False,
                'employee_type': Employee.EmployeeType.OPERATOR,
            },
            {
                'employee_name': 'K.K. Deshmukh',
                'designation_short': 'O/S Opt',
                'cpf_no': '',
                'weekly_off_day': Employee.WeekOffDay.TUESDAY,
                'is_general_duty_operator': False,
                'employee_type': Employee.EmployeeType.OPERATOR,
            },
            {
                'employee_name': 'Suresh General',
                'designation_short': 'O/S Opt',
                'cpf_no': '445566',
                'weekly_off_day': Employee.WeekOffDay.SATURDAY,
                'is_general_duty_operator': True,
                'employee_type': Employee.EmployeeType.OPERATOR,
            },
            {
                'employee_name': 'K.S. Mahajan',
                'designation_short': 'GET',
                'cpf_no': '2926253',
                'weekly_off_day': Employee.WeekOffDay.SATURDAY,
                'is_general_duty_operator': False,
                'employee_type': Employee.EmployeeType.TECH_ENGINEER,
            },
            {
                'employee_name': 'S.L. Thakre',
                'designation_short': 'Prin.Tech',
                'cpf_no': '2071983',
                'weekly_off_day': Employee.WeekOffDay.SUNDAY,
                'is_general_duty_operator': False,
                'employee_type': Employee.EmployeeType.TECH_ENGINEER,
            },
        ]

        created_count = 0
        for payload in employees:
            _, employee_created = Employee.objects.get_or_create(
                substation=substation,
                employee_name=payload['employee_name'],
                defaults=payload,
            )
            if employee_created:
                created_count += 1

        station_status = 'created' if created else 'reused'
        self.stdout.write(
            self.style.SUCCESS(
                f'Sample data loaded successfully. Substation {station_status}; {created_count} new employees added.'
            )
        )

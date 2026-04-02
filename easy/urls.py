from django.urls import path

from . import views

app_name = 'easy'

urlpatterns = [
    path('approval-queue/', views.approval_queue, name='approval_queue'),
    path('substations/', views.substation_master, name='substation_master'),
    path('substations/<int:substation_id>/edit/', views.substation_master, name='substation_edit'),
    path('substations/<int:substation_id>/delete/', views.substation_delete, name='substation_delete'),
    path('employees/<int:employee_id>/edit/', views.substation_master, name='employee_edit'),
    path('employees/<int:employee_id>/delete/', views.employee_delete, name='employee_delete'),
    path('operator-chart/', views.operator_chart, name='operator_chart'),
    path('operator-chart/<int:sheet_id>/pdf/', views.operator_chart_pdf, name='operator_chart_pdf'),
    path('advance-shift/', views.advance_shift_chart, name='advance_shift_chart'),
    path('advance-shift/<int:sheet_id>/pdf/', views.advance_shift_chart_pdf, name='advance_shift_chart_pdf'),
    path('tech-attendance/', views.tech_attendance, name='tech_attendance'),
    path('tech-attendance/<int:sheet_id>/pdf/', views.tech_attendance_pdf, name='tech_attendance_pdf'),
    path('apprentice-attendance/', views.apprentice_attendance, name='apprentice_attendance'),
    path('apprentice-attendance/<int:sheet_id>/pdf/', views.apprentice_attendance_pdf, name='apprentice_attendance_pdf'),
    path('outsource-attendance/', views.outsource_attendance, name='outsource_attendance'),
    path('outsource-attendance/<int:sheet_id>/pdf/', views.outsource_attendance_pdf, name='outsource_attendance_pdf'),
    path('operator-duty-chart/', views.operator_chart),
    path('operator-duty-chart/<int:sheet_id>/pdf/', views.operator_chart_pdf),
    path('advance-shift-chart/', views.advance_shift_chart),
    path('advance-shift-chart/<int:sheet_id>/pdf/', views.advance_shift_chart_pdf),
]

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_SUPER_ADMIN = 'super_admin'
    ROLE_ADMIN = 'admin'
    ROLE_APPROVER = 'approver'
    ROLE_DATA_ENTRY = 'data_entry'
    ROLE_VIEWER = 'viewer'

    ROLE_CHOICES = [
        (ROLE_SUPER_ADMIN, 'Super Admin'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_APPROVER, 'Approver'),
        (ROLE_DATA_ENTRY, 'Data Entry'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    mobile_no = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return f'{self.user.username} - {self.get_role_display()}'


class UserSubstationAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='substation_accesses')
    substation = models.ForeignKey('easy.Substation', on_delete=models.CASCADE, related_name='user_accesses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'substation')
        ordering = ['substation__substation_name']

    def __str__(self):
        return f'{self.user.username} -> {self.substation.substation_name}'


class SignupRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='signup_request')
    full_name = models.CharField(max_length=200)
    mobile_no = models.CharField(max_length=20, blank=True)
    requested_role = models.CharField(max_length=30, choices=UserProfile.ROLE_CHOICES, default=UserProfile.ROLE_DATA_ENTRY)
    requested_substation = models.ForeignKey(
        'easy.Substation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='signup_requests',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} - {self.get_status_display()}'

from django.contrib import admin

from .models import SignupRequest, UserProfile, UserSubstationAccess


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'mobile_no', 'is_active', 'updated_at')
    list_filter = ('role', 'is_active')
    search_fields = ('user__username', 'user__email', 'mobile_no')


@admin.register(UserSubstationAccess)
class UserSubstationAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'substation', 'created_at')
    list_filter = ('substation',)
    search_fields = ('user__username', 'substation__substation_name')


@admin.register(SignupRequest)
class SignupRequestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'requested_role', 'requested_substation', 'status', 'created_at')
    list_filter = ('status', 'requested_role')
    search_fields = ('full_name', 'user__username', 'mobile_no')

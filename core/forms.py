from django import forms
from django.contrib.auth.models import User

from easy.models import AppSetting, Substation
from .models import SignupRequest, UserProfile


class SignupForm(forms.Form):
    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'})
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    mobile_no = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number'})
    )
    requested_substation = forms.ModelChoiceField(
        queryset=Substation.objects.filter(is_active=True).order_by('substation_name'),
        required=False,
        empty_label='Select substation',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'})
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('password1') != cleaned_data.get('password2'):
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password1'],
            email=self.cleaned_data.get('email', ''),
            is_active=False,
        )

        profile = user.profile
        profile.mobile_no = self.cleaned_data.get('mobile_no', '')
        profile.role = UserProfile.ROLE_DATA_ENTRY
        profile.is_active = False
        profile.save()

        SignupRequest.objects.create(
            user=user,
            full_name=self.cleaned_data['full_name'],
            mobile_no=self.cleaned_data.get('mobile_no', ''),
            requested_role=UserProfile.ROLE_DATA_ENTRY,
            requested_substation=self.cleaned_data.get('requested_substation'),
        )
        return user


class UserProfileForm(forms.ModelForm):
    YES_NO_CHOICES = (
        ('True', 'Yes'),
        ('False', 'No'),
    )

    is_active = forms.TypedChoiceField(
        choices=YES_NO_CHOICES,
        coerce=lambda x: str(x) == 'True',
        empty_value=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='User Active',
        help_text='Yes = login allowed, No = login blocked.',
    )

    class Meta:
        model = UserProfile
        fields = ['role', 'mobile_no', 'is_active']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
            'mobile_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_value = self.initial.get('is_active')
        if current_value is None and self.instance.pk:
            current_value = self.instance.is_active
        self.initial['is_active'] = 'True' if current_value else 'False'


class UserAccessForm(forms.Form):
    substations = forms.ModelMultipleChoiceField(
        queryset=Substation.objects.order_by('substation_name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class SignupApprovalForm(forms.Form):
    action = forms.ChoiceField(
        choices=[('approve', 'Approve'), ('reject', 'Reject')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    substations = forms.ModelMultipleChoiceField(
        queryset=Substation.objects.order_by('substation_name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    admin_remark = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'})
    )


class SimpleSettingForm(forms.Form):
    self_signup_enabled = forms.BooleanField(required=False)
    approval_required = forms.BooleanField(required=False)
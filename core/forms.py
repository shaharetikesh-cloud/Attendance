from django import forms
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    IS_ACTIVE_CHOICES = [
        (True, "Yes"),
        (False, "No"),
    ]

    is_active = forms.ChoiceField(
        choices=IS_ACTIVE_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Is Active"
    )

    class Meta:
        model = UserProfile
        fields = ["role", "substations"]

    def __init__(self, *args, **kwargs):
        user_instance = kwargs.pop("user_instance", None)
        super().__init__(*args, **kwargs)

        if user_instance:
            self.fields["is_active"].initial = user_instance.is_active

    def save(self, user_instance=None, commit=True):
        profile = super().save(commit=False)

        if user_instance:
            user_instance.is_active = self.cleaned_data["is_active"] == "True"
            if commit:
                user_instance.save()

        if commit:
            profile.save()

        return profile

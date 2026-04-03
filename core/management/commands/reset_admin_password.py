from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

class Command(BaseCommand):
    help = "Reset password for an existing user or create superuser if missing"

    def handle(self, *args, **kwargs):
        User = get_user_model()

        username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin")
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "")
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")

        if not password:
            self.stdout.write(self.style.ERROR("BOOTSTRAP_ADMIN_PASSWORD is not set"))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if created:
            user.is_staff = True
            user.is_superuser = True

        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(f"Password set for user: {username}"))
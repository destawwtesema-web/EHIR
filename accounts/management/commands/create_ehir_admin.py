from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Create or update the EHIRS Ministry Administrator"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="admin",
            help="Username for the Ministry Admin",
        )
        parser.add_argument(
            "--email",
            default="admin@ehir.gov.et",
            help="Email address for the Ministry Admin",
        )
        parser.add_argument(
            "--password",
            required=True,
            help="Password for the Ministry Admin",
        )

    def handle(self, *args, **options):

        User = get_user_model()

        username = options["username"]
        email = options["email"]
        password = options["password"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role": UserProfile.Role.MINISTRY_ADMIN,
                "organization": None,
                "facility": None,
                "active": True,
            },
        )

        profile.role = UserProfile.Role.MINISTRY_ADMIN
        profile.organization = None
        profile.facility = None
        profile.active = True
        profile.save()

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ministry Admin '{username}' created successfully."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ministry Admin '{username}' updated successfully."
                )
            )

        if profile_created:
            self.stdout.write(
                self.style.SUCCESS(
                    "EHIRS Ministry Admin profile created."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "EHIRS Ministry Admin profile updated."
                )
            )
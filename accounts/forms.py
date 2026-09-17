
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from core.models import OrganizationUnit, Facility
from .models import UserProfile


User = get_user_model()


class UserManagementForm(forms.Form):
    """
    Form used by Ministry, Regional, and Sub-city administrators
    to create and edit EHIRS users.
    """

    # ==========================================================
    # USER INFORMATION
    # ==========================================================

    username = forms.CharField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter username",
            }
        ),
    )

    first_name = forms.CharField(
        max_length=150,
        required=False,
        label="First name",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "First name",
            }
        ),
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
        label="Last name",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Last name",
            }
        ),
    )

    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@example.com",
            }
        ),
    )

    # ==========================================================
    # ROLE
    # ==========================================================

    role = forms.ChoiceField(
        choices=UserProfile.Role.choices,
        label="Role",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    # ==========================================================
    # ORGANIZATION
    # ==========================================================

    organization = forms.ModelChoiceField(
        queryset=OrganizationUnit.objects.none(),
        required=False,
        label="Organization",
        empty_label="Select organization",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    # ==========================================================
    # FACILITY
    # ==========================================================

    facility = forms.ModelChoiceField(
        queryset=Facility.objects.none(),
        required=False,
        label="Facility",
        empty_label="Select facility",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    # ==========================================================
    # ACTIVE
    # ==========================================================

    active = forms.BooleanField(
        required=False,
        initial=True,
        label="Active user",
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
            }
        ),
    )

    # ==========================================================
    # PASSWORD
    # ==========================================================

    password = forms.CharField(
        required=False,
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter password",
                "autocomplete": "new-password",
            }
        ),
    )

    password_confirm = forms.CharField(
        required=False,
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirm password",
                "autocomplete": "new-password",
            }
        ),
    )

    # ==========================================================
    # INITIALIZATION
    # ==========================================================

    def __init__(
        self,
        *args,
        manager_profile=None,
        instance=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.manager_profile = manager_profile
        self.instance = instance

        # ------------------------------------------------------
        # NO MANAGER
        # ------------------------------------------------------

        if not manager_profile:
            self.fields["role"].choices = []

            self.fields[
                "organization"
            ].queryset = OrganizationUnit.objects.none()

            self.fields[
                "facility"
            ].queryset = Facility.objects.none()

            return

        # ------------------------------------------------------
        # ORGANIZATION OPTIONS
        # ------------------------------------------------------

        self.fields[
            "organization"
        ].queryset = (
            manager_profile
            .accessible_organizations()
            .select_related("parent")
            .order_by("name")
        )

        # ------------------------------------------------------
        # FACILITY OPTIONS
        # ------------------------------------------------------

        self.fields[
            "facility"
        ].queryset = (
            manager_profile
            .accessible_facilities()
            .select_related("organization")
            .order_by("name")
        )

        # ------------------------------------------------------
        # ROLE OPTIONS
        #
        # Ministry:
        #   Ministry
        #   Region
        #   Sub-city
        #   Facility
        #
        # Region:
        #   Region
        #   Sub-city
        #   Facility
        #
        # Sub-city:
        #   Sub-city
        #   Facility
        # ------------------------------------------------------

        if manager_profile.is_ministry_admin():

            allowed_roles = [
                UserProfile.Role.MINISTRY_ADMIN,
                UserProfile.Role.REGION_ADMIN,
                UserProfile.Role.SUBCITY_ADMIN,
                UserProfile.Role.FACILITY_USER,
            ]

        elif manager_profile.is_region_admin():

            allowed_roles = [
                UserProfile.Role.REGION_ADMIN,
                UserProfile.Role.SUBCITY_ADMIN,
                UserProfile.Role.FACILITY_USER,
            ]

        elif manager_profile.is_subcity_admin():

            allowed_roles = [
                UserProfile.Role.SUBCITY_ADMIN,
                UserProfile.Role.FACILITY_USER,
            ]

        else:

            allowed_roles = []

        self.fields["role"].choices = [
            choice
            for choice in UserProfile.Role.choices
            if choice[0] in allowed_roles
        ]

        # ------------------------------------------------------
        # EDIT EXISTING USER
        # ------------------------------------------------------

        if instance:

            user = instance.user

            self.fields["username"].initial = user.username

            self.fields["first_name"].initial = (
                user.first_name
            )

            self.fields["last_name"].initial = (
                user.last_name
            )

            self.fields["email"].initial = (
                user.email
            )

            self.fields["role"].initial = (
                instance.role
            )

            self.fields["organization"].initial = (
                instance.organization_id
            )

            self.fields["facility"].initial = (
                instance.facility_id
            )

            self.fields["active"].initial = (
                instance.active and user.is_active
            )

            self.fields["password"].help_text = (
                "Leave blank to keep the current password."
            )

        # ------------------------------------------------------
        # CREATE NEW USER
        # ------------------------------------------------------

        else:

            self.fields["password"].required = True

            self.fields[
                "password_confirm"
            ].required = True

    # ==========================================================
    # USERNAME VALIDATION
    # ==========================================================

    def clean_username(self):

        username = (
            self.cleaned_data["username"]
            .strip()
        )

        if not username:

            raise ValidationError(
                "Username is required."
            )

        users = User.objects.filter(
            username__iexact=username
        )

        # When editing, exclude the current user.
        if self.instance:

            users = users.exclude(
                pk=self.instance.user_id
            )

        if users.exists():

            raise ValidationError(
                "This username is already in use."
            )

        return username

    # ==========================================================
    # MAIN VALIDATION
    # ==========================================================

    def clean(self):

        cleaned = super().clean()

        role = cleaned.get("role")
        organization = cleaned.get("organization")
        facility = cleaned.get("facility")

        password = cleaned.get("password")
        password_confirm = cleaned.get(
            "password_confirm"
        )

        # ======================================================
        # PASSWORD VALIDATION
        # ======================================================

        if password or password_confirm:

            if password != password_confirm:

                self.add_error(
                    "password_confirm",
                    "Passwords do not match.",
                )

            if password and len(password) < 8:

                self.add_error(
                    "password",
                    "Password must contain at least 8 characters.",
                )

        # ======================================================
        # MANAGER VALIDATION
        # ======================================================

        if self.manager_profile:

            if not self.manager_profile.active:

                raise ValidationError(
                    "Your administrator account is inactive."
                )

        # ======================================================
        # ROLE AUTHORIZATION
        # ======================================================

        if self.manager_profile:

            if self.manager_profile.is_ministry_admin():

                allowed_roles = {
                    UserProfile.Role.MINISTRY_ADMIN,
                    UserProfile.Role.REGION_ADMIN,
                    UserProfile.Role.SUBCITY_ADMIN,
                    UserProfile.Role.FACILITY_USER,
                }

            elif self.manager_profile.is_region_admin():

                allowed_roles = {
                    UserProfile.Role.REGION_ADMIN,
                    UserProfile.Role.SUBCITY_ADMIN,
                    UserProfile.Role.FACILITY_USER,
                }

            elif self.manager_profile.is_subcity_admin():

                allowed_roles = {
                    UserProfile.Role.SUBCITY_ADMIN,
                    UserProfile.Role.FACILITY_USER,
                }

            else:

                allowed_roles = set()

            if role not in allowed_roles:

                self.add_error(
                    "role",
                    "You do not have permission to create or assign this role.",
                )

        # ======================================================
        # ORGANIZATION & FACILITY VALIDATION BY ROLE
        # ======================================================

        if role == UserProfile.Role.MINISTRY_ADMIN:

            if facility:
                self.add_error(
                    "facility",
                    "A Ministry Admin cannot be assigned to a facility.",
                )

        elif role == UserProfile.Role.REGION_ADMIN:

            if not organization:
                self.add_error(
                    "organization",
                    "A Regional Admin must be assigned to a Region.",
                )
            elif (
                organization.unit_type
                != OrganizationUnit.UnitType.REGION
            ):
                self.add_error(
                    "organization",
                    "A Regional Admin must be assigned to a Region organization.",
                )

            if facility:
                self.add_error(
                    "facility",
                    "A Regional Admin cannot be assigned to a facility.",
                )

        elif role == UserProfile.Role.SUBCITY_ADMIN:

            if not organization:
                self.add_error(
                    "organization",
                    "A Sub-city Admin must be assigned to a Sub-city.",
                )
            elif (
                organization.unit_type
                != OrganizationUnit.UnitType.SUBCITY
            ):
                self.add_error(
                    "organization",
                    "A Sub-city Admin must be assigned to a Sub-city organization.",
                )

            if facility:
                self.add_error(
                    "facility",
                    "A Sub-city Admin cannot be assigned to a facility.",
                )

        elif role == UserProfile.Role.FACILITY_USER:

            if not facility:
                self.add_error(
                    "facility",
                    "A Facility User must be assigned to a facility.",
                )

        # ======================================================
        # ACCESSIBILITY CHECK
        # ======================================================

        if self.manager_profile:

            if organization and not self.manager_profile.can_access_organization(organization):
                self.add_error(
                    "organization",
                    "You do not have permission to assign users to this organization.",
                )

            if facility and not self.manager_profile.can_access_facility(facility):
                self.add_error(
                    "facility",
                    "You do not have permission to assign users to this facility.",
                )

        return cleaned

    # ==========================================================
    # SAVE
    # ==========================================================

    def save(self):
        """
        Create or update User and UserProfile instances.
        """
        cleaned = self.cleaned_data
        role = cleaned.get("role")
        organization = cleaned.get("organization")
        facility = cleaned.get("facility")
        active = cleaned.get("active", True)
        username = cleaned.get("username")
        first_name = cleaned.get("first_name", "")
        last_name = cleaned.get("last_name", "")
        email = cleaned.get("email", "")
        password = cleaned.get("password")

        from django.db import transaction

        with transaction.atomic():
            if self.instance:
                profile = self.instance
                user = profile.user
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.is_active = active
                if password:
                    user.set_password(password)
                user.save()

                profile.role = role
                if role == UserProfile.Role.FACILITY_USER and facility:
                    profile.organization = facility.organization
                    profile.facility = facility
                else:
                    profile.organization = organization
                    profile.facility = facility
                profile.active = active
                profile.save()
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=active,
                )
                if role == UserProfile.Role.FACILITY_USER and facility:
                    organization = facility.organization
                profile = UserProfile.objects.create(
                    user=user,
                    role=role,
                    organization=organization,
                    facility=facility,
                    active=active,
                )

        return profile


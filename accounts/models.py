
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import OrganizationUnit, Facility


class UserProfile(models.Model):

    class Role(models.TextChoices):
        MINISTRY_ADMIN = "MINISTRY_ADMIN", "Ministry Admin"
        REGION_ADMIN = "REGION_ADMIN", "Regional Admin"
        SUBCITY_ADMIN = "SUBCITY_ADMIN", "Sub-city Admin"
        FACILITY_USER = "FACILITY_USER", "Facility User"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    organization = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="user_profiles",
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="user_profiles",
    )

    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    # ==========================================================
    # ROLE CHECKS
    # ==========================================================

    def is_ministry_admin(self):
        return self.role == self.Role.MINISTRY_ADMIN

    def is_region_admin(self):
        return self.role == self.Role.REGION_ADMIN

    def is_subcity_admin(self):
        return self.role == self.Role.SUBCITY_ADMIN

    def is_facility_user(self):
        return self.role == self.Role.FACILITY_USER

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def clean(self):
        """
        Validate that organization and facility assignments
        are consistent with the user's role.
        """

        # ------------------------------------------------------
        # MINISTRY ADMIN
        # ------------------------------------------------------

        if self.is_ministry_admin():

            if self.facility:
                raise ValidationError(
                    "A Ministry Admin cannot be assigned to a facility."
                )

            return

        # ------------------------------------------------------
        # REGIONAL ADMIN
        # ------------------------------------------------------

        if self.is_region_admin():

            if not self.organization:
                raise ValidationError(
                    "A Regional Admin must be assigned to a Region."
                )

            if (
                self.organization.unit_type
                != OrganizationUnit.UnitType.REGION
            ):
                raise ValidationError(
                    "A Regional Admin must be assigned to a Region."
                )

            if self.facility:
                raise ValidationError(
                    "A Regional Admin cannot be assigned to a facility."
                )

        # ------------------------------------------------------
        # SUB-CITY ADMIN
        # ------------------------------------------------------

        elif self.is_subcity_admin():

            if not self.organization:
                raise ValidationError(
                    "A Sub-city Admin must be assigned to a Sub-city."
                )

            if (
                self.organization.unit_type
                != OrganizationUnit.UnitType.SUBCITY
            ):
                raise ValidationError(
                    "A Sub-city Admin must be assigned to a Sub-city."
                )

            if self.facility:
                raise ValidationError(
                    "A Sub-city Admin cannot be assigned to a facility."
                )

        # ------------------------------------------------------
        # FACILITY USER
        # ------------------------------------------------------

        elif self.is_facility_user():

            if not self.facility:
                raise ValidationError(
                    "A Facility User must be assigned to a facility."
                )

            if not self.facility.active:
                raise ValidationError(
                    "The assigned facility is not active."
                )

            # Facility user's organization must always
            # match the facility's organization.
            if (
                self.organization
                and self.organization_id
                != self.facility.organization_id
            ):
                raise ValidationError(
                    "The user's organization must match "
                    "the facility's reporting organization."
                )

    # ==========================================================
    # SAVE
    # ==========================================================

    def save(self, *args, **kwargs):
        """
        Automatically synchronize facility user's
        organization with the facility.
        """

        if self.is_facility_user() and self.facility:
            self.organization = self.facility.organization

        self.full_clean()

        super().save(*args, **kwargs)

    # ==========================================================
    # ORGANIZATION ACCESS
    # ==========================================================

    def can_access_organization(self, organization):
        """
        Check whether this user can access an organization.
        """

        if not self.active:
            return False

        if not organization:
            return False

        if not organization.active:
            return False

        # Ministry Admin can access everything.
        if self.is_ministry_admin():
            return True

        if not self.organization:
            return False

        # Everyone can access their own organization.
        if organization.id == self.organization_id:
            return True

        # Regional Admin can access descendants.
        if self.is_region_admin():

            current = organization.parent

            while current:

                if current.id == self.organization_id:
                    return True

                current = current.parent

        return False

    # ==========================================================
    # FACILITY ACCESS
    # ==========================================================

    def can_access_facility(self, facility):
        """
        Check whether this user can access a facility.
        """

        if not self.active:
            return False

        if not facility:
            return False

        if not facility.active:
            return False

        # Ministry sees every facility.
        if self.is_ministry_admin():
            return True

        # Facility user sees only their own facility.
        if self.is_facility_user():

            return (
                self.facility_id is not None
                and self.facility_id == facility.id
            )

        if not facility.organization:
            return False

        # Region/Sub-city access.
        return self.can_access_organization(
            facility.organization
        )

    # ==========================================================
    # ACCESSIBLE ORGANIZATIONS
    # ==========================================================

    def accessible_organizations(self):
        """
        Return organizations this user can access.
        """

        queryset = OrganizationUnit.objects.filter(
            active=True
        )

        # ------------------------------------------------------
        # MINISTRY
        # ------------------------------------------------------

        if self.is_ministry_admin():
            return queryset

        if not self.organization:
            return queryset.none()

        # ------------------------------------------------------
        # REGION
        #
        # Region
        # ├── Sub-cities
        # └── Other direct organizations
        # ------------------------------------------------------

        if self.is_region_admin():

            return queryset.filter(
                Q(id=self.organization_id)
                |
                Q(parent=self.organization)
                |
                Q(parent__parent=self.organization)
            ).distinct()

        # ------------------------------------------------------
        # SUB-CITY
        # ------------------------------------------------------

        if self.is_subcity_admin():

            return queryset.filter(
                id=self.organization_id
            )

        # ------------------------------------------------------
        # FACILITY USER
        # ------------------------------------------------------

        return queryset.none()

    # ==========================================================
    # ACCESSIBLE FACILITIES
    # ==========================================================

    def accessible_facilities(self):
        """
        Return facilities this user can access.
        """

        queryset = (
            Facility.objects
            .filter(active=True)
            .select_related("organization")
        )

        # ------------------------------------------------------
        # MINISTRY
        # ------------------------------------------------------

        if self.is_ministry_admin():
            return queryset

        # ------------------------------------------------------
        # FACILITY USER
        # ------------------------------------------------------

        if self.is_facility_user():

            if self.facility_id:

                return queryset.filter(
                    id=self.facility_id
                )

            return queryset.none()

        if not self.organization:
            return queryset.none()

        # ------------------------------------------------------
        # REGION
        #
        # Region
        # ├── Special Hospitals
        # └── Sub-cities
        #       └── Health Centers
        # ------------------------------------------------------

        if self.is_region_admin():

            return queryset.filter(
                Q(
                    organization=self.organization
                )
                |
                Q(
                    organization__parent=self.organization
                )
            ).distinct()

        # ------------------------------------------------------
        # SUB-CITY
        # ------------------------------------------------------

        if self.is_subcity_admin():

            return queryset.filter(
                organization=self.organization
            )

        return queryset.none()

    # ==========================================================
    # ACCESSIBLE USER PROFILES
    # ==========================================================

    def accessible_user_profiles(self):
        """
        Return the user profiles that this user is
        allowed to manage.
        """

        queryset = (
            UserProfile.objects
            .select_related(
                "user",
                "organization",
                "facility",
            )
        )

        # ------------------------------------------------------
        # MINISTRY ADMIN
        #
        # Ministry can manage all users.
        # ------------------------------------------------------

        if self.is_ministry_admin():

            return queryset

        # ------------------------------------------------------
        # REGION ADMIN
        #
        # Can manage:
        #   - users assigned directly to the region
        #   - users assigned to sub-cities
        #   - facility users in the region
        # ------------------------------------------------------

        if self.is_region_admin():

            if not self.organization_id:
                return queryset.none()

            return queryset.filter(
                Q(
                    organization=self.organization
                )
                |
                Q(
                    organization__parent=self.organization
                )
                |
                Q(
                    facility__organization=self.organization
                )
                |
                Q(
                    facility__organization__parent=self.organization
                )
            ).distinct()

        # ------------------------------------------------------
        # SUB-CITY ADMIN
        #
        # Can manage:
        #   - users assigned to their sub-city
        #   - facility users belonging to their sub-city
        # ------------------------------------------------------

        if self.is_subcity_admin():

            if not self.organization_id:
                return queryset.none()

            return queryset.filter(
                Q(
                    organization=self.organization
                )
                |
                Q(
                    facility__organization=self.organization
                )
            ).distinct()

        # ------------------------------------------------------
        # FACILITY USER
        #
        # Facility users cannot manage users.
        # ------------------------------------------------------

        return queryset.none()

    # ==========================================================
    # CAN MANAGE USER
    # ==========================================================

    def can_manage_user(self, target_profile):
        """
        Check whether this user can manage another user.
        """

        if not self.active:
            return False

        if not target_profile:
            return False

        if not target_profile.active:
            # An inactive user can still be managed by an
            # authorized administrator.
            pass

        # A user cannot manage themselves through this
        # management permission.
        if target_profile.id == self.id:
            return False

        # Ministry Admin can manage everyone.
        if self.is_ministry_admin():
            return True

        # ------------------------------------------------------
        # REGION ADMIN
        # ------------------------------------------------------

        if self.is_region_admin():

            if not self.organization_id:
                return False

            # Never allow regional admin to manage Ministry Admin.
            if target_profile.is_ministry_admin():
                return False

            # Direct organization match.
            if (
                target_profile.organization_id
                == self.organization_id
            ):
                return True

            # Target's organization is inside this region.
            if target_profile.organization:

                current = target_profile.organization.parent

                while current:

                    if current.id == self.organization_id:
                        return True

                    current = current.parent

            # Facility user's facility belongs to this region.
            if target_profile.facility:

                facility_org = (
                    target_profile.facility.organization
                )

                if facility_org:

                    if facility_org.id == self.organization_id:
                        return True

                    current = facility_org.parent

                    while current:

                        if current.id == self.organization_id:
                            return True

                        current = current.parent

            return False

        # ------------------------------------------------------
        # SUB-CITY ADMIN
        # ------------------------------------------------------

        if self.is_subcity_admin():

            if not self.organization_id:
                return False

            # Cannot manage Ministry or Regional Admin.
            if target_profile.is_ministry_admin():
                return False

            if target_profile.is_region_admin():
                return False

            # Direct sub-city organization.
            if (
                target_profile.organization_id
                == self.organization_id
            ):
                return True

            # Facility user belonging to this sub-city.
            if target_profile.facility:

                if (
                    target_profile.facility.organization_id
                    == self.organization_id
                ):
                    return True

            return False

        # Facility users cannot manage anyone.
        return False

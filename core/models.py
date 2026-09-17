from django.core.exceptions import ValidationError
from django.db import models


class OrganizationUnit(models.Model):

    class UnitType(models.TextChoices):
        MINISTRY = "MINISTRY", "Ministry of Health"
        REGION = "REGION", "Region"
        ZONE = "ZONE", "Zone"
        SUBCITY = "SUBCITY", "Sub-city"
        WOREDA = "WOREDA", "Woreda"
        OTHER = "OTHER", "Other"

    name = models.CharField(
        max_length=200
    )

    code = models.CharField(
        max_length=50,
        unique=True
    )

    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children"
    )

    active = models.BooleanField(
        default=True
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def clean(self):

        # -------------------------------------------------
        # MINISTRY
        # -------------------------------------------------
        if self.unit_type == self.UnitType.MINISTRY:

            if self.parent:
                raise ValidationError(
                    "Ministry of Health cannot have a parent."
                )

            return

        # Every other organization must have a parent
        if not self.parent:
            raise ValidationError(
                "This organization unit must have a parent."
            )

        parent_type = self.parent.unit_type

        # -------------------------------------------------
        # REGION
        # Region reports directly to Ministry
        # -------------------------------------------------
        if self.unit_type == self.UnitType.REGION:

            if parent_type != self.UnitType.MINISTRY:
                raise ValidationError(
                    "A Region must belong directly to the Ministry of Health."
                )

        # -------------------------------------------------
        # SUB-CITY
        # Sub-city belongs to Region
        # -------------------------------------------------
        elif self.unit_type == self.UnitType.SUBCITY:

            if parent_type != self.UnitType.REGION:
                raise ValidationError(
                    "A Sub-city must belong to a Region."
                )

        # -------------------------------------------------
        # ZONE
        # Zone belongs to Region
        # -------------------------------------------------
        elif self.unit_type == self.UnitType.ZONE:

            if parent_type != self.UnitType.REGION:
                raise ValidationError(
                    "A Zone must belong to a Region."
                )

        # -------------------------------------------------
        # WOREDA
        # Woreda belongs to Sub-city or Zone
        # -------------------------------------------------
        elif self.unit_type == self.UnitType.WOREDA:

            if parent_type not in [
                self.UnitType.SUBCITY,
                self.UnitType.ZONE,
            ]:
                raise ValidationError(
                    "A Woreda must belong to a Sub-city or Zone."
                )

        # -------------------------------------------------
        # OTHER
        # -------------------------------------------------
        elif self.unit_type == self.UnitType.OTHER:

            # OTHER organizations can belong to Ministry
            # or Region.
            if parent_type not in [
                self.UnitType.MINISTRY,
                self.UnitType.REGION,
            ]:
                raise ValidationError(
                    "An Other organization must belong to the Ministry or a Region."
                )

    def save(self, *args, **kwargs):

        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):

        return f"{self.name} ({self.get_unit_type_display()})"


class Facility(models.Model):

    class FacilityType(models.TextChoices):

        SPECIAL_HOSPITAL = (
            "SPECIAL_HOSPITAL",
            "Special Hospital"
        )

        HEALTH_CENTER = (
            "HEALTH_CENTER",
            "Health Center"
        )

    name = models.CharField(
        max_length=200
    )

    code = models.CharField(
        max_length=50,
        unique=True
    )

    facility_type = models.CharField(
        max_length=30,
        choices=FacilityType.choices
    )

    organization = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="facilities"
    )

    active = models.BooleanField(
        default=True
    )

    description = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def clean(self):

        if not self.organization:
            raise ValidationError(
                "A facility must have a reporting organization."
            )

        organization_type = self.organization.unit_type

        # -------------------------------------------------
        # SPECIAL HOSPITAL
        # Must report directly to Region
        # -------------------------------------------------
        if self.facility_type == self.FacilityType.SPECIAL_HOSPITAL:

            if organization_type != OrganizationUnit.UnitType.REGION:
                raise ValidationError(
                    "A Special Hospital must report directly to a Region."
                )

        # -------------------------------------------------
        # HEALTH CENTER
        # Must report directly to Sub-city
        # -------------------------------------------------
        elif self.facility_type == self.FacilityType.HEALTH_CENTER:

            if organization_type != OrganizationUnit.UnitType.SUBCITY:
                raise ValidationError(
                    "A Health Center must report directly to a Sub-city."
                )

    def save(self, *args, **kwargs):

        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):

        return f"{self.name} ({self.code})"
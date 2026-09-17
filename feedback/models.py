
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import OrganizationUnit, Facility


class Feedback(models.Model):
    """
    EHIRS Feedback and Communication System.

    Communication hierarchy:

        MINISTRY
            ↕
        REGION
            ↕
        SUB-CITY / ZONE / WOREDA
            ↕
        FACILITY

    Allowed communication routes:

    UPWARD
        Facility -> Sub-city / Zone / Woreda
        Facility -> Region
        Sub-city / Zone / Woreda -> Region
        Region -> Ministry

    DOWNWARD
        Ministry -> Region
        Region -> Sub-city / Zone / Woreda
        Region -> Facility
        Sub-city / Zone / Woreda -> Facility

    Facility-to-Facility communication is not allowed.

    Each Feedback record stores BOTH sides of the communication:

        Sender
            - user
            - level
            - organization
            - facility when applicable

        Receiver
            - level
            - organization
            - facility when applicable

    This allows EHIRS to answer questions such as:

        "Which facility sent this feedback?"

        "Which sub-city sent this feedback?"

        "Which region received it?"

        "Which feedback came from facilities to the region?"

        "Which feedback did the Ministry send to Addis Ababa Region?"

    Feedback can also belong to an AssessmentPeriod.

    Replies belong to the same reporting period as their parent
    feedback and must follow the communication route.
    """

    # =========================================================
    # CHOICES
    # =========================================================

    class Category(models.TextChoices):
        ASSESSMENT = "ASSESSMENT", "Assessment"
        LQAS = "LQAS", "LQAS"
        DASHBOARD = "DASHBOARD", "Dashboard"
        REPORTS = "REPORTS", "Reports"
        TECHNICAL = "TECHNICAL", "Technical Problem"
        DATA = "DATA", "Data Quality"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        IMPORTANT = "IMPORTANT", "Important"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class SenderLevel(models.TextChoices):
        FACILITY = "FACILITY", "Facility"
        SUBCITY = "SUBCITY", "Sub-city / Zone / Woreda"
        REGION = "REGION", "Region"
        MINISTRY = "MINISTRY", "Ministry"

    class RecipientLevel(models.TextChoices):
        FACILITY = "FACILITY", "Facility"
        SUBCITY = "SUBCITY", "Sub-city / Zone / Woreda"
        REGION = "REGION", "Region"
        MINISTRY = "MINISTRY", "Ministry"

    # =========================================================
    # CONVERSATION
    # =========================================================

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )

    # =========================================================
    # REPORTING PERIOD
    # =========================================================

    period = models.ForeignKey(
        "assessments.AssessmentPeriod",
        on_delete=models.PROTECT,
        related_name="feedback_messages",
        null=True,
        blank=True,
    )

    # =========================================================
    # BASIC INFORMATION
    # =========================================================

    subject = models.CharField(
        max_length=255,
    )

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    message = models.TextField()

    # =========================================================
    # SENDER
    # =========================================================

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_feedback",
    )

    sender_level = models.CharField(
        max_length=20,
        choices=SenderLevel.choices,
    )

    sender_organization = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="feedback_sent_from",
        null=True,
        blank=True,
    )

    sender_facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="feedback_sent",
        null=True,
        blank=True,
    )

    # =========================================================
    # RECEIVER
    # =========================================================

    recipient_level = models.CharField(
        max_length=20,
        choices=RecipientLevel.choices,
    )

    recipient_organization = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="feedback_received",
        null=True,
        blank=True,
    )

    recipient_facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="feedback_received",
        null=True,
        blank=True,
    )

    # =========================================================
    # STATUS
    # =========================================================

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # =========================================================
    # RATING
    # =========================================================

    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    # =========================================================
    # RESOLUTION
    # =========================================================

    resolution_note = models.TextField(
        blank=True,
        default="",
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resolved_feedback",
        null=True,
        blank=True,
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # =========================================================
    # READ TRACKING
    # =========================================================

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # =========================================================
    # DATABASE META
    # =========================================================

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["status"],
            ),
            models.Index(
                fields=["priority"],
            ),
            models.Index(
                fields=["category"],
            ),
            models.Index(
                fields=["sender_level"],
            ),
            models.Index(
                fields=["recipient_level"],
            ),
            models.Index(
                fields=["sender_organization"],
            ),
            models.Index(
                fields=["recipient_organization"],
            ),
            models.Index(
                fields=["sender_facility"],
            ),
            models.Index(
                fields=["recipient_facility"],
            ),
            models.Index(
                fields=["period"],
            ),
            models.Index(
                fields=["created_at"],
            ),
            models.Index(
                fields=["parent"],
            ),
        ]

    # =========================================================
    # HIERARCHY HELPERS
    # =========================================================

    @staticmethod
    def organization_is_descendant(organization, ancestor):
        """
        Return True when organization is the same as ancestor
        or exists somewhere below ancestor.
        """

        if not organization or not ancestor:
            return False

        current = organization

        visited = set()

        while current:
            if current.pk in visited:
                return False

            visited.add(current.pk)

            if current.pk == ancestor.pk:
                return True

            current = current.parent

        return False

    @staticmethod
    def get_region(organization):
        """
        Find the Region above the supplied organization.

        Examples:

            Region
                -> returns Region

            Sub-city
                -> returns parent Region

            Woreda
                -> returns Region through its ancestors
        """

        if not organization:
            return None

        current = organization
        visited = set()

        while current:

            if current.pk in visited:
                return None

            visited.add(current.pk)

            if current.unit_type == OrganizationUnit.UnitType.REGION:
                return current

            current = current.parent

        return None

    @staticmethod
    def is_lower_organization(unit):
        """
        Return True for Sub-city, Zone or Woreda.
        """

        if not unit:
            return False

        return unit.unit_type in [
            OrganizationUnit.UnitType.SUBCITY,
            OrganizationUnit.UnitType.ZONE,
            OrganizationUnit.UnitType.WOREDA,
        ]

    # =========================================================
    # ENDPOINT HELPERS
    # =========================================================

    def sender_endpoint(self):
        """
        Return the unique communication endpoint of the sender.

        Facility:
            ("FACILITY", facility_id)

        Organization:
            ("ORGANIZATION", organization_id)
        """

        if self.sender_level == self.SenderLevel.FACILITY:
            return (
                "FACILITY",
                self.sender_facility_id,
            )

        return (
            "ORGANIZATION",
            self.sender_organization_id,
        )

    def recipient_endpoint(self):
        """
        Return the unique communication endpoint of the receiver.

        Facility:
            ("FACILITY", facility_id)

        Organization:
            ("ORGANIZATION", organization_id)
        """

        if self.recipient_level == self.RecipientLevel.FACILITY:
            return (
                "FACILITY",
                self.recipient_facility_id,
            )

        return (
            "ORGANIZATION",
            self.recipient_organization_id,
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def clean(self):
        """
        Validate the complete Feedback communication route.
        """

        errors = {}

        # =====================================================
        # BASIC REQUIRED DATA
        # =====================================================

        if not self.subject or not self.subject.strip():
            errors["subject"] = "A feedback subject is required."

        if not self.message or not self.message.strip():
            errors["message"] = "A feedback message is required."

        # =====================================================
        # RATING
        # =====================================================

        if self.rating is not None:

            if self.rating < 1 or self.rating > 5:
                errors["rating"] = (
                    "Rating must be between 1 and 5."
                )

        # =====================================================
        # SENDER LEVEL VALIDATION
        # =====================================================

        valid_sender_levels = {
            self.SenderLevel.FACILITY,
            self.SenderLevel.SUBCITY,
            self.SenderLevel.REGION,
            self.SenderLevel.MINISTRY,
        }

        if self.sender_level not in valid_sender_levels:
            errors["sender_level"] = (
                "Invalid sender level."
            )

        # =====================================================
        # SENDER VALIDATION
        # =====================================================

        if self.sender_level == self.SenderLevel.FACILITY:

            if not self.sender_facility:
                errors["sender_facility"] = (
                    "A facility sender must have a facility."
                )

            if not self.sender_organization:
                errors["sender_organization"] = (
                    "A facility sender must have an organization."
                )

            if (
                self.sender_facility
                and self.sender_organization
                and self.sender_facility.organization_id
                != self.sender_organization_id
            ):
                errors["sender_organization"] = (
                    "The sender organization does not match "
                    "the facility's reporting organization."
                )

        elif self.sender_level == self.SenderLevel.SUBCITY:

            if not self.sender_organization:
                errors["sender_organization"] = (
                    "A Sub-city, Zone or Woreda sender "
                    "must have an organization."
                )

            elif not self.is_lower_organization(
                self.sender_organization
            ):
                errors["sender_organization"] = (
                    "The sender organization must be a "
                    "Sub-city, Zone or Woreda."
                )

            if self.sender_facility:
                errors["sender_facility"] = (
                    "A Sub-city, Zone or Woreda sender "
                    "cannot have a sender facility."
                )

        elif self.sender_level == self.SenderLevel.REGION:

            if not self.sender_organization:
                errors["sender_organization"] = (
                    "A Regional sender must have a Region."
                )

            elif (
                self.sender_organization.unit_type
                != OrganizationUnit.UnitType.REGION
            ):
                errors["sender_organization"] = (
                    "The sender organization must be a Region."
                )

            if self.sender_facility:
                errors["sender_facility"] = (
                    "A Regional sender cannot have a sender facility."
                )

        elif self.sender_level == self.SenderLevel.MINISTRY:

            if not self.sender_organization:
                errors["sender_organization"] = (
                    "A Ministry sender must have the Ministry "
                    "organization recorded."
                )

            elif (
                self.sender_organization.unit_type
                != OrganizationUnit.UnitType.MINISTRY
            ):
                errors["sender_organization"] = (
                    "The sender organization must be the "
                    "Ministry of Health."
                )

            if self.sender_facility:
                errors["sender_facility"] = (
                    "A Ministry sender cannot have a sender facility."
                )

        # =====================================================
        # RECEIVER LEVEL VALIDATION
        # =====================================================

        valid_recipient_levels = {
            self.RecipientLevel.FACILITY,
            self.RecipientLevel.SUBCITY,
            self.RecipientLevel.REGION,
            self.RecipientLevel.MINISTRY,
        }

        if self.recipient_level not in valid_recipient_levels:
            errors["recipient_level"] = (
                "Invalid recipient level."
            )

        # =====================================================
        # RECEIVER VALIDATION
        # =====================================================

        if self.recipient_level == self.RecipientLevel.FACILITY:

            if not self.recipient_facility:
                errors["recipient_facility"] = (
                    "A facility recipient must have a facility."
                )

            if not self.recipient_organization:
                errors["recipient_organization"] = (
                    "A facility recipient must have an organization."
                )

            if (
                self.recipient_facility
                and self.recipient_organization
                and self.recipient_facility.organization_id
                != self.recipient_organization_id
            ):
                errors["recipient_organization"] = (
                    "The recipient organization does not match "
                    "the facility's reporting organization."
                )

        elif self.recipient_level == self.RecipientLevel.SUBCITY:

            if not self.recipient_organization:
                errors["recipient_organization"] = (
                    "A Sub-city, Zone or Woreda recipient "
                    "must have an organization."
                )

            elif not self.is_lower_organization(
                self.recipient_organization
            ):
                errors["recipient_organization"] = (
                    "The recipient must be a Sub-city, "
                    "Zone or Woreda."
                )

            if self.recipient_facility:
                errors["recipient_facility"] = (
                    "An organizational recipient cannot "
                    "have a recipient facility."
                )

        elif self.recipient_level == self.RecipientLevel.REGION:

            if not self.recipient_organization:
                errors["recipient_organization"] = (
                    "A Regional recipient must have a Region."
                )

            elif (
                self.recipient_organization.unit_type
                != OrganizationUnit.UnitType.REGION
            ):
                errors["recipient_organization"] = (
                    "The recipient organization must be a Region."
                )

            if self.recipient_facility:
                errors["recipient_facility"] = (
                    "A Regional recipient cannot have "
                    "a recipient facility."
                )

        elif self.recipient_level == self.RecipientLevel.MINISTRY:

            if not self.recipient_organization:
                errors["recipient_organization"] = (
                    "A Ministry recipient must have the "
                    "Ministry organization."
                )

            elif (
                self.recipient_organization.unit_type
                != OrganizationUnit.UnitType.MINISTRY
            ):
                errors["recipient_organization"] = (
                    "The recipient organization must be "
                    "the Ministry of Health."
                )

            if self.recipient_facility:
                errors["recipient_facility"] = (
                    "A Ministry recipient cannot have "
                    "a recipient facility."
                )

        # =====================================================
        # STOP IF BASIC ENDPOINT DATA IS INVALID
        # =====================================================

        if errors:
            raise ValidationError(errors)

        # =====================================================
        # FACILITY -> FACILITY
        # =====================================================

        if (
            self.sender_level == self.SenderLevel.FACILITY
            and self.recipient_level
            == self.RecipientLevel.FACILITY
        ):
            errors["recipient_facility"] = (
                "Facilities cannot directly send feedback "
                "to another facility."
            )

        # =====================================================
        # FACILITY -> SUBCITY / ZONE / WOREDA
        # =====================================================

        if (
            self.sender_level == self.SenderLevel.FACILITY
            and self.recipient_level
            == self.RecipientLevel.SUBCITY
        ):

            recipient = self.recipient_organization
            sender_facility = self.sender_facility

            if sender_facility and recipient:

                if (
                    sender_facility.organization_id
                    != recipient.pk
                ):
                    errors["recipient_organization"] = (
                        "The selected organization is not the "
                        "reporting organization of this facility."
                    )

        # =====================================================
        # FACILITY -> REGION
        # =====================================================

        if (
            self.sender_level == self.SenderLevel.FACILITY
            and self.recipient_level
            == self.RecipientLevel.REGION
        ):

            recipient = self.recipient_organization
            sender_facility = self.sender_facility

            if sender_facility and recipient:

                facility_region = self.get_region(
                    sender_facility.organization
                )

                if facility_region != recipient:
                    errors["recipient_organization"] = (
                        "The selected Region is not responsible "
                        "for this facility."
                    )

        # =====================================================
        # SUBCITY / ZONE / WOREDA -> REGION
        # =====================================================

        if (
            self.sender_level == self.SenderLevel.SUBCITY
            and self.recipient_level
            == self.RecipientLevel.REGION
        ):

            sender_organization = self.sender_organization
            recipient = self.recipient_organization

            sender_region = self.get_region(
                sender_organization
            )

            if sender_region != recipient:
                errors["recipient_organization"] = (
                    "The selected Region is not the parent "
                    "Region of the sender organization."
                )

        # =====================================================
        # SUBCITY / ZONE / WOREDA -> FACILITY
        # =====================================================

        if (
            self.sender_level == self.SenderLevel.SUBCITY
            and self.recipient_level
            == self.RecipientLevel.FACILITY
        ):

            sender_organization = self.sender_organization
            recipient_facility = self.recipient_facility

            if (
                sender_organization
                and recipient_facility
                and recipient_facility.organization_id
                != sender_organization.pk
            ):
                errors["recipient_facility"] = (
                    "The selected facility does not belong "
                    "to the sender organization."
                )

        # ================================

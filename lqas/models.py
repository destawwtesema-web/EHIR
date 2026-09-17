
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models

from core.models import Facility


# ============================================================
# LQAS ASSESSMENT
# ============================================================

class LQASAssessment(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="lqas_assessments",
    )

    year = models.PositiveIntegerField()

    period = models.CharField(
        max_length=50,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    matched_count = models.PositiveIntegerField(
        default=0,
    )

    total_elements = models.PositiveIntegerField(
        default=0,
    )

    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="created_lqas_assessments",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-year",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "facility",
                    "year",
                    "period",
                ],
                name="unique_lqas_facility_year_period",
            ),
        ]

    # ========================================================
    # CALCULATE LQAS RESULT
    # ========================================================

    def calculate_result(self):
        """
        Calculate the overall LQAS accuracy percentage.
        """

        responses = self.responses.all()

        self.total_elements = responses.count()

        self.matched_count = responses.filter(
            match=True
        ).count()

        if self.total_elements > 0:
            self.percentage = (
                Decimal(self.matched_count)
                / Decimal(self.total_elements)
            ) * Decimal("100")
        else:
            self.percentage = Decimal("0.00")

        self.percentage = self.percentage.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return self.percentage

    def save(self, *args, **kwargs):
        """
        Recalculate the summary whenever an existing
        assessment is saved.
        """

        if self.pk:
            self.calculate_result()

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.facility.name} - "
            f"{self.year} - "
            f"{self.period}"
        )


# ============================================================
# LQAS RESPONSE
# ============================================================

class LQASResponse(models.Model):
    """
    One row in the LQAS table.

    Data Element Name is FREE TEXT.

    There is NO fixed/master data-element list.
    The facility types the data element name manually.
    """

    assessment = models.ForeignKey(
        LQASAssessment,
        on_delete=models.CASCADE,
        related_name="responses",
    )

    # ========================================================
    # DATA ELEMENT NAME
    # ========================================================
    # Facility enters the name manually.

    data_element_name = models.CharField(
        max_length=255,
    )

    # ========================================================
    # COUNTS
    # ========================================================

    tally_sheet = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    register = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    report = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # ========================================================
    # AUTOMATIC MATCH
    # ========================================================

    match = models.BooleanField(
        default=False,
    )

    class Meta:
        ordering = [
            "id",
        ]

    # ========================================================
    # CALCULATE MATCH
    # ========================================================

    def calculate_match(self):
        """
        Match = YES only when all three counts are entered
        and all three counts are exactly equal.
        """

        if (
            self.tally_sheet is None
            or self.register is None
            or self.report is None
        ):
            self.match = False

        else:
            self.match = (
                self.tally_sheet
                == self.register
                == self.report
            )

        return self.match

    # ========================================================
    # VALIDATION
    # ========================================================

    def clean(self):
        """
        Validate the LQAS response.
        """

        if not self.data_element_name.strip():
            raise ValidationError(
                "Data Element Name is required."
            )

        values = [
            self.tally_sheet,
            self.register,
            self.report,
        ]

        for value in values:
            if value is not None and value < 0:
                raise ValidationError(
                    "LQAS counts cannot be negative."
                )

    # ========================================================
    # SAVE
    # ========================================================

    def save(self, *args, **kwargs):
        """
        Validate and automatically calculate Match.
        """

        self.full_clean()

        self.calculate_match()

        super().save(*args, **kwargs)

    # ========================================================
    # DISPLAY NAME
    # ========================================================

    def __str__(self):
        return (
            f"{self.assessment} - "
            f"{self.data_element_name}"
        )

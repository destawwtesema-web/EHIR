
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

from core.models import Facility


# =============================================================
# CONSTANTS
# =============================================================

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")


# =============================================================
# ASSESSMENT SECTION
# =============================================================

class AssessmentSection(models.Model):
    """
    Main assessment sections.

    Example:

        A = HIS Structure and Resources = 30%
        B = Data Quality = 30%
        C = Data Use = 40%
    """

    code = models.CharField(
        max_length=10,
        unique=True
    )

    name = models.CharField(
        max_length=255
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    order = models.PositiveIntegerField(
        default=1
    )

    active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "order",
            "code",
        ]

    def clean(self):
        """
        Validate section configuration.
        """

        if self.weight < ZERO:
            raise ValidationError({
                "weight": "Section weight cannot be negative."
            })

        if self.weight > ONE_HUNDRED:
            raise ValidationError({
                "weight": "Section weight cannot be greater than 100."
            })

    def __str__(self):
        return f"{self.code}. {self.name}"


# =============================================================
# THEMATIC AREA
# =============================================================

class AssessmentThematicArea(models.Model):
    """
    Groups indicators within a section.
    """

    section = models.ForeignKey(
        AssessmentSection,
        on_delete=models.PROTECT,
        related_name="thematic_areas"
    )

    code = models.CharField(
        max_length=20
    )

    name = models.CharField(
        max_length=500
    )

    maximum_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=ZERO
    )

    order = models.PositiveIntegerField(
        default=1
    )

    active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "section__order",
            "order",
            "code",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "section",
                    "code",
                ],
                name="unique_thematic_area_code"
            )
        ]

    def clean(self):

        if self.maximum_score < ZERO:
            raise ValidationError({
                "maximum_score": (
                    "Maximum score cannot be negative."
                )
            })

    def update_maximum_score(self):
        """
        Calculate and save the maximum score of this thematic area
        from its active indicators.
        """

        total = ZERO

        indicators = self.indicators.filter(
            active=True
        )

        for indicator in indicators:
            total += (
                indicator.maximum_score
                or ZERO
            )

        total = total.quantize(
            Decimal("0.01")
        )

        self.maximum_score = total

        if self.pk:
            AssessmentThematicArea.objects.filter(
                pk=self.pk
            ).update(
                maximum_score=total
            )

        return total

    def __str__(self):
        return f"{self.code}. {self.name}"


# =============================================================
# ASSESSMENT INDICATOR
# =============================================================

class AssessmentIndicator(models.Model):
    """
    Individual assessment question / indicator.
    """

    class ResponseType(models.TextChoices):

        YES_NO = (
            "YES_NO",
            "Yes / No"
        )

        CHOICE = (
            "CHOICE",
            "Multiple Choice"
        )

        NUMERIC = (
            "NUMERIC",
            "Numeric"
        )

        CALCULATION = (
            "CALCULATION",
            "Calculated"
        )

        CONDUCTED_CHECK = (
            "CONDUCTED_CHECK",
            "Conducted / Not Conducted"
        )

    class CalculationType(models.TextChoices):

        NONE = (
            "NONE",
            "No Calculation"
        )

        PERCENTAGE = (
            "PERCENTAGE",
            "Percentage"
        )

        RATIO = (
            "RATIO",
            "Numerator / Denominator"
        )

        PERIOD_MONTHS = (
            "PERIOD_MONTHS",
            "Based on Period Months"
        )

        CUSTOM = (
            "CUSTOM",
            "Custom Calculation"
        )

    thematic_area = models.ForeignKey(
        AssessmentThematicArea,
        on_delete=models.PROTECT,
        related_name="indicators"
    )

    code = models.CharField(
        max_length=30
    )

    question = models.TextField()

    response_type = models.CharField(
        max_length=30,
        choices=ResponseType.choices,
        default=ResponseType.YES_NO
    )

    calculation_type = models.CharField(
        max_length=30,
        choices=CalculationType.choices,
        default=CalculationType.NONE
    )

    maximum_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=ZERO
    )

    help_text = models.TextField(
        blank=True
    )

    order = models.PositiveIntegerField(
        default=1
    )

    active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "thematic_area__section__order",
            "thematic_area__order",
            "order",
            "code",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "thematic_area",
                    "code",
                ],
                name="unique_indicator_code"
            )
        ]

    def clean(self):

        if self.maximum_score < ZERO:
            raise ValidationError({
                "maximum_score": (
                    "Maximum score cannot be negative."
                )
            })

        # Ratio calculations require calculation response type.
        if (
            self.calculation_type
            == self.CalculationType.RATIO
            and self.response_type
            not in [
                self.ResponseType.NUMERIC,
                self.ResponseType.CALCULATION,
            ]
        ):

            raise ValidationError({
                "response_type": (
                    "Ratio calculation indicators must use "
                    "Numeric or Calculated response type."
                )
            })

    def save(self, *args, **kwargs):

        super().save(
            *args,
            **kwargs
        )

        # Update thematic area maximum score.
        if self.thematic_area_id:
            self.thematic_area.update_maximum_score()

    def delete(self, *args, **kwargs):

        thematic_area = self.thematic_area

        super().delete(
            *args,
            **kwargs
        )

        if thematic_area:
            thematic_area.update_maximum_score()

    def __str__(self):
        return (
            f"{self.code}. "
            f"{self.question[:100]}"
        )


# =============================================================
# INDICATOR OPTIONS
# =============================================================

class IndicatorOption(models.Model):
    """
    Possible answers for choice-based indicators.

    Examples:

        YES = 1
        NO = 0

    Or:

        ONLINE = 2
        OFFLINE = 1
        NO = 0
    """

    indicator = models.ForeignKey(
        AssessmentIndicator,
        on_delete=models.CASCADE,
        related_name="options"
    )

    code = models.CharField(
        max_length=30
    )

    label = models.CharField(
        max_length=500
    )

    score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=ZERO
    )

    order = models.PositiveIntegerField(
        default=1
    )

    active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "order",
            "code",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "indicator",
                    "code",
                ],
                name="unique_indicator_option_code"
            )
        ]

    def clean(self):

        if self.score < ZERO:
            raise ValidationError({
                "score": "Option score cannot be negative."
            })

        if (
            self.indicator_id
            and self.score
            > self.indicator.maximum_score
        ):

            raise ValidationError({
                "score": (
                    "Option score cannot be greater than "
                    "the indicator maximum score."
                )
            })

    def __str__(self):
        return (
            f"{self.label} "
            f"({self.score})"
        )


# =============================================================
# ASSESSMENT PERIOD
# =============================================================

class AssessmentPeriod(models.Model):
    """
    Defines the reporting period.

    Monthly   = 1 month
    Quarterly = 3 months
    Biannual  = 6 months
    Annual    = 12 months
    """

    class PeriodType(models.TextChoices):

        MONTHLY = (
            "MONTHLY",
            "Monthly"
        )

        QUARTERLY = (
            "QUARTERLY",
            "Quarterly"
        )

        BIANNUAL = (
            "BIANNUAL",
            "Biannual"
        )

        ANNUAL = (
            "ANNUAL",
            "Annual"
        )

    year = models.PositiveIntegerField()

    period_type = models.CharField(
        max_length=20,
        choices=PeriodType.choices
    )

    period_number = models.PositiveIntegerField(
        default=1
    )

    name = models.CharField(
        max_length=100
    )

    start_month = models.PositiveIntegerField()

    end_month = models.PositiveIntegerField()

    active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "-year",
            "start_month",
            "period_type",
            "period_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "year",
                    "period_type",
                    "period_number",
                ],
                name="unique_assessment_period"
            )
        ]

    def clean(self):

        errors = {}

        # -----------------------------------------------------
        # YEAR
        # -----------------------------------------------------

        if self.year < 1900:

            errors["year"] = (
                "Year must be 1900 or later."
            )

        # -----------------------------------------------------
        # MONTH RANGE
        # -----------------------------------------------------

        if not 1 <= self.start_month <= 12:

            errors["start_month"] = (
                "Start month must be between 1 and 12."
            )

        if not 1 <= self.end_month <= 12:

            errors["end_month"] = (
                "End month must be between 1 and 12."
            )

        if (
            1 <= self.start_month <= 12
            and 1 <= self.end_month <= 12
            and self.start_month > self.end_month
        ):

            errors["end_month"] = (
                "End month cannot be earlier than "
                "start month."
            )

        # -----------------------------------------------------
        # PERIOD NUMBER
        # -----------------------------------------------------

        valid_period_numbers = {

            self.PeriodType.MONTHLY: range(
                1,
                13
            ),

            self.PeriodType.QUARTERLY: range(
                1,
                5
            ),

            self.PeriodType.BIANNUAL: range(
                1,
                3
            ),

            self.PeriodType.ANNUAL: range(
                1,
                2
            ),
        }

        if (
            self.period_type
            in valid_period_numbers
            and self.period_number
            not in valid_period_numbers[
                self.period_type
            ]
        ):

            errors["period_number"] = (
                f"Invalid period number for "
                f"{self.get_period_type_display()}."
            )

        # -----------------------------------------------------
        # EXPECTED MONTH COUNT
        # -----------------------------------------------------

        expected_months = {

            self.PeriodType.MONTHLY: 1,

            self.PeriodType.QUARTERLY: 3,

            self.PeriodType.BIANNUAL: 6,

            self.PeriodType.ANNUAL: 12,
        }

        if (
            self.period_type
            in expected_months
            and 1 <= self.start_month <= 12
            and 1 <= self.end_month <= 12
            and self.start_month <= self.end_month
        ):

            actual_months = (
                self.end_month
                - self.start_month
                + 1
            )

            expected = expected_months[
                self.period_type
            ]

            if actual_months != expected:

                errors["end_month"] = (
                    f"{self.get_period_type_display()} "
                    f"must contain exactly "
                    f"{expected} month(s)."
                )

        # -----------------------------------------------------
        # PERIOD POSITION VALIDATION
        # -----------------------------------------------------

        if self.period_type == self.PeriodType.MONTHLY:

            if (
                self.start_month
                != self.period_number
                or self.end_month
                != self.period_number
            ):

                errors["period_number"] = (
                    "Monthly period number must match "
                    "the month number."
                )

        elif self.period_type == self.PeriodType.QUARTERLY:

            expected_start = (
                (self.period_number - 1) * 3
            ) + 1

            expected_end = (
                self.period_number * 3
            )

            if (
                self.start_month != expected_start
                or self.end_month != expected_end
            ):

                errors["period_number"] = (
                    f"Quarter {self.period_number} must cover "
                    f"months {expected_start} to {expected_end}."
                )

        elif self.period_type == self.PeriodType.BIANNUAL:

            expected_start = (
                (self.period_number - 1) * 6
            ) + 1

            expected_end = (
                self.period_number * 6
            )

            if (
                self.start_month != expected_start
                or self.end_month != expected_end
            ):

                errors["period_number"] = (
                    f"Biannual period {self.period_number} "
                    f"must cover months "
                    f"{expected_start} to {expected_end}."
                )

        elif self.period_type == self.PeriodType.ANNUAL:

            if (
                self.period_number != 1
                or self.start_month != 1
                or self.end_month != 12
            ):

                errors["period_number"] = (
                    "Annual period must be period number 1 "
                    "and cover January to December."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.year} - "
            f"{self.name}"
        )


# =============================================================
# ASSESSMENT
# =============================================================

class Assessment(models.Model):
    """
    One assessment for one facility and one reporting period.

    Workflow:

        DRAFT
          ↓
        SUBMITTED
          ↓
        REVIEWED
          ↓
        APPROVED

    Or:

        SUBMITTED
          ↓
        RETURNED
          ↓
        Facility corrects
          ↓
        SUBMITTED
    """

    class Status(models.TextChoices):

        DRAFT = (
            "DRAFT",
            "Draft"
        )

        SUBMITTED = (
            "SUBMITTED",
            "Submitted"
        )

        REVIEWED = (
            "REVIEWED",
            "Reviewed"
        )

        APPROVED = (
            "APPROVED",
            "Approved"
        )

        RETURNED = (
            "RETURNED",
            "Returned"
        )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name="assessments"
    )

    period = models.ForeignKey(
        AssessmentPeriod,
        on_delete=models.PROTECT,
        related_name="assessments"
    )

    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="created_assessments"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )

    # ---------------------------------------------------------
    # SUBMISSION
    # ---------------------------------------------------------

    submitted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # ---------------------------------------------------------
    # REVIEW
    # ---------------------------------------------------------

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    review_comment = models.TextField(
        blank=True
    )

    # ---------------------------------------------------------
    # APPROVAL
    # ---------------------------------------------------------

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    approval_comment = models.TextField(
        blank=True
    )

    # ---------------------------------------------------------
    # RETURN
    # ---------------------------------------------------------

    returned_at = models.DateTimeField(
        null=True,
        blank=True
    )

    return_reason = models.TextField(
        blank=True
    )

    # ---------------------------------------------------------
    # SCORE
    # ---------------------------------------------------------

    total_score = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=ZERO
    )

    # ---------------------------------------------------------
    # TIMESTAMPS
    # ---------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = [
            "-period__year",
            "-period__start_month",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "facility",
                    "period",
                ],
                name="one_assessment_per_facility_period"
            )
        ]

    def clean(self):

        if self.total_score < ZERO:
            raise ValidationError({
                "total_score": (
                    "Total score cannot be negative."
                )
            })

        if self.total_score > ONE_HUNDRED:
            raise ValidationError({
                "total_score": (
                    "Total score cannot exceed 100."
                )
            })

    def calculate_section_score(self, section):
        """
        Calculate weighted score for one section.

        Example:

            Achieved score = 24
            Maximum score = 27
            Section weight = 30

            24 / 27 × 30 = 26.67
        """

        indicators = (
            AssessmentIndicator.objects
            .filter(
                thematic_area__section=section,
                active=True,
            )
        )

        maximum_score = sum(
            (
                indicator.maximum_score
                or ZERO
                for indicator in indicators
            ),
            ZERO
        )

        responses = self.responses.filter(
            indicator__thematic_area__section=section,
            indicator__active=True,
        )

        achieved_score = sum(
            (
                response.calculated_score
                or ZERO
                for response in responses
            ),
            ZERO
        )

        if maximum_score <= ZERO:
            return ZERO

        # Prevent invalid scores.
        achieved_score = max(
            achieved_score,
            ZERO
        )

        achieved_score = min(
            achieved_score,
            maximum_score
        )

        weighted_score = (
            achieved_score
            / maximum_score
        ) * section.weight

        return weighted_score.quantize(
            Decimal("0.01")
        )

    def calculate_total_score(self):
        """
        Calculate the final assessment score.

        Expected configuration:

            Section A = 30
            Section B = 30
            Section C = 40

            Total = 100
        """

        total = ZERO

        sections = (
            AssessmentSection.objects
            .filter(
                active=True
            )
            .order_by(
                "order",
                "code"
            )
        )

        for section in sections:

            total += (
                self.calculate_section_score(
                    section
                )
            )

        total = max(
            total,
            ZERO
        )

        total = min(
            total,
            ONE_HUNDRED
        )

        self.total_score = total.quantize(
            Decimal("0.01")
        )

        return self.total_score

    def update_total_score(self):
        """
        Calculate and save the assessment total score.
        """

        self.calculate_total_score()

        if self.pk:

            Assessment.objects.filter(
                pk=self.pk
            ).update(
                total_score=self.total_score
            )

        return self.total_score

    def __str__(self):
        return (
            f"{self.facility.name} - "
            f"{self.period}"
        )


# =============================================================
# ASSESSMENT RESPONSE
# =============================================================

class AssessmentResponse(models.Model):
    """
    Stores the answer to an indicator.

    Supports:

        - Yes / No
        - Multiple Choice
        - Numeric values
        - Numerator / Denominator
        - Calculated values
        - Conducted / Not Conducted
    """

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    indicator = models.ForeignKey(
        AssessmentIndicator,
        on_delete=models.PROTECT,
        related_name="responses"
    )

    selected_option = models.ForeignKey(
        IndicatorOption,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_responses"
    )

    numeric_value = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )

    numerator = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )

    denominator = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )

    calculated_score = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=ZERO
    )

    conducted = models.BooleanField(
        null=True,
        blank=True
    )

    notes = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "assessment",
                    "indicator",
                ],
                name="one_response_per_indicator"
            )
        ]

    def clean(self):

        errors = {}

        # -----------------------------------------------------
        # SELECTED OPTION VALIDATION
        # -----------------------------------------------------

        if self.selected_option:

            if (
                self.selected_option.indicator_id
                != self.indicator_id
            ):

                errors["selected_option"] = (
                    "The selected option does not belong "
                    "to this indicator."
                )

            elif not self.selected_option.active:

                errors["selected_option"] = (
                    "The selected option is inactive."
                )

        # -----------------------------------------------------
        # NUMERIC VALUE
        # -----------------------------------------------------

        if (
            self.numeric_value is not None
            and self.numeric_value < ZERO
        ):

            errors["numeric_value"] = (
                "Numeric value cannot be negative."
            )

        # -----------------------------------------------------
        # NUMERATOR
        # -----------------------------------------------------

        if (
            self.numerator is not None
            and self.numerator < ZERO
        ):

            errors["numerator"] = (
                "Numerator cannot be negative."
            )

        # -----------------------------------------------------
        # DENOMINATOR
        # -----------------------------------------------------

        if (
            self.denominator is not None
            and self.denominator < ZERO
        ):

            errors["denominator"] = (
                "Denominator cannot be negative."
            )

        # -----------------------------------------------------
        # NUMERATOR <= DENOMINATOR
        # -----------------------------------------------------

        if (
            self.numerator is not None
            and self.denominator is not None
            and self.denominator > ZERO
            and self.numerator > self.denominator
        ):

            errors["numerator"] = (
                "Numerator cannot be greater than "
                "denominator."
            )

        # -----------------------------------------------------
        # RATIO VALIDATION
        # -----------------------------------------------------

        if (
            self.indicator_id
            and self.indicator.calculation_type
            == AssessmentIndicator.CalculationType.RATIO
        ):

            if self.numerator is None:

                errors["numerator"] = (
                    "Numerator is required for ratio "
                    "calculation."
                )

            if self.denominator is None:

                errors["denominator"] = (
                    "Denominator is required for ratio "
                    "calculation."
                )

        # -----------------------------------------------------
        # YES / NO OR CHOICE
        # -----------------------------------------------------

        if (
            self.indicator_id
            and self.indicator.response_type
            in [
                AssessmentIndicator.ResponseType.YES_NO,
                AssessmentIndicator.ResponseType.CHOICE,
            ]
            and self.selected_option is None
        ):

            errors["selected_option"] = (
                "Please select an answer."
            )

        # -----------------------------------------------------
        # CONDUCTED CHECK
        # -----------------------------------------------------

        if (
            self.indicator_id
            and self.indicator.response_type
            == AssessmentIndicator.ResponseType.CONDUCTED_CHECK
            and self.conducted is None
        ):

            errors["conducted"] = (
                "Please specify whether the activity "
                "was conducted."
            )

        if errors:
            raise ValidationError(errors)

    def calculate_ratio_score(self):
        """
        Calculate ratio score.

        Example:

            Numerator   = 80
            Denominator = 100
            Maximum     = 5

            Score = 80 / 100 × 5 = 4
        """

        if (
            self.numerator is None
            or self.denominator is None
            or self.denominator <= ZERO
        ):

            return ZERO

        percentage = (
            self.numerator
            / self.denominator
        ) * ONE_HUNDRED

        maximum_score = (
            self.indicator.maximum_score
            or ZERO
        )

        score = (
            percentage
            / ONE_HUNDRED
        ) * maximum_score

        score = max(
            score,
            ZERO
        )

        score = min(
            score,
            maximum_score
        )

        return score.quantize(
            Decimal("0.01")
        )

    def calculate_score(self):
        """
        Calculate score for this response.
        """

        score = ZERO

        # -----------------------------------------------------
        # NOT CONDUCTED = ZERO
        # -----------------------------------------------------

        if self.conducted is False:

            score = ZERO

        # -----------------------------------------------------
        # SELECTED OPTION
        # ------------------

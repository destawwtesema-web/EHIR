from django import forms

from .models import (
    Assessment,
    AssessmentIndicator,
    AssessmentResponse,
)


class AssessmentResponseForm(forms.ModelForm):

    class Meta:
        model = AssessmentResponse
        fields = [
            "selected_option",
            "numeric_value",
            "numerator",
            "denominator",
            "conducted",
            "notes",
        ]

        widgets = {
            "selected_option": forms.RadioSelect(),
            "numeric_value": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
            "numerator": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "denominator": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "conducted": forms.RadioSelect(
                choices=[
                    (True, "Yes"),
                    (False, "No"),
                ]
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Optional notes",
                }
            ),
        }

    def __init__(self, *args, indicator=None, **kwargs):

        super().__init__(*args, **kwargs)

        self.indicator = indicator

        if not indicator:
            return

        response_type = indicator.response_type
        calculation_type = indicator.calculation_type

        # -------------------------
        # YES / NO
        # -------------------------

        if response_type == (
            AssessmentIndicator.ResponseType.YES_NO
        ):
            self.fields["selected_option"].required = True

        # -------------------------
        # MULTIPLE CHOICE
        # -------------------------

        elif response_type == (
            AssessmentIndicator.ResponseType.CHOICE
        ):
            self.fields["selected_option"].required = True

        # -------------------------
        # NUMERIC
        # -------------------------

        elif response_type == (
            AssessmentIndicator.ResponseType.NUMERIC
        ):
            self.fields["numeric_value"].required = True
            self.fields["selected_option"].widget = (
                forms.HiddenInput()
            )

        # -------------------------
        # CALCULATION
        # -------------------------

        elif response_type == (
            AssessmentIndicator.ResponseType.CALCULATION
        ):
            self.fields["numerator"].required = True
            self.fields["denominator"].required = True
            self.fields["selected_option"].widget = (
                forms.HiddenInput()
            )

        # -------------------------
        # CONDUCTED CHECK
        # -------------------------

        elif response_type == (
            AssessmentIndicator.ResponseType.CONDUCTED_CHECK
        ):
            self.fields["conducted"].required = True

            self.fields["selected_option"].widget = (
                forms.HiddenInput()
            )

        # -------------------------
        # Calculation type also
        # determines numerator /
        # denominator visibility.
        # -------------------------

        if calculation_type == (
            AssessmentIndicator.CalculationType.RATIO
        ):
            self.fields["numerator"].required = True
            self.fields["denominator"].required = True

            self.fields["selected_option"].widget = (
                forms.HiddenInput()
            )

        # Hide unused fields initially.
        if response_type not in [
            AssessmentIndicator.ResponseType.NUMERIC,
        ]:
            if calculation_type != (
                AssessmentIndicator.CalculationType.RATIO
            ):
                self.fields["numeric_value"].widget = (
                    forms.HiddenInput()
                )

        if calculation_type != (
            AssessmentIndicator.CalculationType.RATIO
        ):
            self.fields["numerator"].widget = (
                forms.HiddenInput()
            )
            self.fields["denominator"].widget = (
                forms.HiddenInput()
            )
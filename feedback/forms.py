
from django import forms
from django.forms.models import construct_instance

from .models import Feedback


# ============================================================
# CREATE FEEDBACK FORM
# ============================================================

class FeedbackCreateForm(forms.ModelForm):
    """
    Form for creating a new Feedback conversation.

    The logged-in user's sender information is NOT entered
    manually in this form.

    views.py determines:
        - sender user
        - sender level
        - sender organization
        - sender facility
        - recipient level
        - recipient organization
        - recipient facility

    The receiver field contains server-generated choices only.

    The reporting period is selected by the user.

    Because Feedback.clean() requires sender/recipient endpoint
    information, _post_clean() intentionally delays model-level
    validation. The complete Feedback object is validated when
    views.py has populated all endpoint information and calls
    save().
    """

    # ========================================================
    # RECEIVER
    # ========================================================

    recipient = forms.ChoiceField(
        label="Receiver",
        required=True,
        choices=(),
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    # ========================================================
    # MODEL
    # ========================================================

    class Meta:
        model = Feedback

        fields = [
            "period",
            "recipient",
            "subject",
            "category",
            "priority",
            "message",
            "rating",
        ]

        widgets = {
            "period": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter feedback subject",
                    "maxlength": 255,
                }
            ),

            "category": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "priority": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 7,
                    "placeholder": (
                        "Write your feedback, question, "
                        "problem or request..."
                    ),
                }
            ),

            "rating": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1,
                    "max": 5,
                    "step": 1,
                    "placeholder": "Optional: 1–5",
                }
            ),
        }

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(
        self,
        *args,
        recipient_choices=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # ----------------------------------------------------
        # Receiver choices
        # ----------------------------------------------------
        #
        # These choices MUST come from views.py.
        #
        # The user should never be able to manually choose
        # an arbitrary organization/facility ID.
        # ----------------------------------------------------

        if recipient_choices:
            self.fields["recipient"].choices = recipient_choices
        else:
            self.fields["recipient"].choices = [
                ("", "Select receiver...")
            ]

        self.fields["recipient"].help_text = (
            "Select the organization or facility that "
            "should receive this feedback."
        )

        # ----------------------------------------------------
        # Reporting period
        # ----------------------------------------------------

        self.fields["period"].required = False

        self.fields["period"].empty_label = (
            "Select reporting period..."
        )

        self.fields["period"].help_text = (
            "Select the reporting period related to "
            "this feedback."
        )

        # ----------------------------------------------------
        # Rating
        # ----------------------------------------------------

        self.fields["rating"].help_text = (
            "Optional rating from 1 to 5."
        )

        # ----------------------------------------------------
        # Labels
        # ----------------------------------------------------

        self.fields["period"].label = "Reporting Period"
        self.fields["subject"].label = "Subject"
        self.fields["category"].label = "Category"
        self.fields["priority"].label = "Priority"
        self.fields["message"].label = "Feedback Message"
        self.fields["rating"].label = "Rating"

    # ========================================================
    # RECIPIENT VALIDATION
    # ========================================================

    def clean_recipient(self):
        """
        Validate that a receiver was selected.

        The actual receiver must also be checked in views.py
        against the server-generated choices.

        This provides protection against a user manually
        posting an unauthorized receiver value.
        """

        recipient = self.cleaned_data.get("recipient")

        if not recipient:
            raise forms.ValidationError(
                "Please select a receiver."
            )

        return recipient

    # ========================================================
    # PERIOD VALIDATION
    # ========================================================

    def clean_period(self):
        """
        Validate the selected reporting period.

        An inactive period cannot be selected.
        """

        period = self.cleaned_data.get("period")

        # Period is optional.
        if period is None:
            return None

        if not period.active:
            raise forms.ValidationError(
                "The selected reporting period is not active."
            )

        return period

    # ========================================================
    # SUBJECT VALIDATION
    # ========================================================

    def clean_subject(self):
        subject = self.cleaned_data.get("subject")

        if subject is None:
            raise forms.ValidationError(
                "Please enter a subject."
            )

        subject = subject.strip()

        if not subject:
            raise forms.ValidationError(
                "Please enter a subject."
            )

        if len(subject) > 255:
            raise forms.ValidationError(
                "The subject cannot exceed 255 characters."
            )

        return subject

    # ========================================================
    # MESSAGE VALIDATION
    # ========================================================

    def clean_message(self):
        message = self.cleaned_data.get("message")

        if message is None:
            raise forms.ValidationError(
                "Please enter your feedback."
            )

        message = message.strip()

        if not message:
            raise forms.ValidationError(
                "Please enter your feedback."
            )

        return message

    # ========================================================
    # RATING VALIDATION
    # ========================================================

    def clean_rating(self):
        """
        Validate the optional 1–5 rating.

        This validation is performed here because model
        validation is intentionally delayed in _post_clean().
        """

        rating = self.cleaned_data.get("rating")

        if rating in [None, ""]:
            return None

        if rating < 1 or rating > 5:
            raise forms.ValidationError(
                "Rating must be between 1 and 5."
            )

        return rating

    # ========================================================
    # MODEL FORM VALIDATION
    # ========================================================

    def _post_clean(self):
        """
        Construct the Feedback instance without executing
        Feedback.clean() prematurely.

        Django normally performs model validation from
        ModelForm._post_clean().

        That cannot happen here because sender and recipient
        endpoint information is populated by views.py after
        the form has been validated.

        Feedback.save() performs complete model validation
        after all endpoint information has been assigned.
        """

        opts = self._meta

        # Django 6.1 may return a set here.
        exclude = set(
            self._get_validation_exclusions()
        )

        # ----------------------------------------------------
        # Fields populated by views.py
        # ----------------------------------------------------

        exclude.update(
            {
                "sender",
                "sender_level",
                "sender_organization",
                "sender_facility",
                "recipient_level",
                "recipient_organization",
                "recipient_facility",
                "status",
                "resolution_note",
                "resolved_by",
                "resolved_at",
                "read_at",
                "parent",
            }
        )

        # ----------------------------------------------------
        # Construct model instance from cleaned form data.
        # ----------------------------------------------------

        self.instance = construct_instance(
            self,
            self.instance,
            opts.fields,
            opts.exclude,
        )

        # ----------------------------------------------------
        # IMPORTANT
        # ----------------------------------------------------
        #
        # Do NOT call:
        #
        #     self.instance.full_clean()
        #
        # here.
        #
        # views.py still needs to populate:
        #
        #     sender
        #     sender_level
        #     sender_organization
        #     sender_facility
        #     recipient_level
        #     recipient_organization
        #     recipient_facility
        #     status
        #
        # Feedback.save() calls full_clean() after that.
        # ----------------------------------------------------


# ============================================================
# REPLY FORM
# ============================================================

class FeedbackReplyForm(forms.Form):
    """
    Form for replying to an existing Feedback conversation.

    The sender and recipient of the reply are determined by
    views.py from the existing conversation endpoint.
    """

    message = forms.CharField(
        label="Reply",
        required=True,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 6,
                "placeholder": "Write your reply...",
            }
        ),
    )

    # ========================================================
    # MESSAGE VALIDATION
    # ========================================================

    def clean_message(self):
        message = self.cleaned_data.get("message")

        if message is None:
            raise forms.ValidationError(
                "Please enter a reply."
            )

        message = message.strip()

        if not message:
            raise forms.ValidationError(
                "Please enter a reply."
            )

        return message


# ============================================================
# STATUS FORM
# ============================================================

class FeedbackStatusForm(forms.Form):
    """
    Form for updating Feedback status.

    Authorization is handled by views.py.

    This form only validates the submitted status and
    resolution note.
    """

    status = forms.ChoiceField(
        label="Status",
        choices=Feedback.Status.choices,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    resolution_note = forms.CharField(
        label="Resolution Note",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": (
                    "Enter resolution details when "
                    "resolving or closing feedback..."
                ),
            }
        ),
    )

    # ========================================================
    # STATUS VALIDATION
    # ========================================================

    def clean_status(self):
        status = self.cleaned_data.get("status")

        valid_statuses = {
            value
            for value, label in Feedback.Status.choices
        }

        if status not in valid_statuses:
            raise forms.ValidationError(
                "Invalid feedback status."
            )

        return status

    # ========================================================
    # RESOLUTION NOTE VALIDATION
    # ========================================================

    def clean_resolution_note(self):
        note = self.cleaned_data.get(
            "resolution_note"
        )

        if note is None:
            return ""

        return note.strip()

    # ========================================================
    # FORM-LEVEL VALIDATION
    # ========================================================

    def clean(self):
        """
        Require a resolution note when feedback is being
        resolved or closed.
        """

        cleaned_data = super().clean()

        status = cleaned_data.get("status")

        resolution_note = cleaned_data.get(
            "resolution_note",
            "",
        )

        if status in [
            Feedback.Status.RESOLVED,
            Feedback.Status.CLOSED,
        ]:
            if not resolution_note:
                self.add_error(
                    "resolution_note",
                    (
                        "Please enter a resolution note "
                        "when resolving or closing feedback."
                    ),
                )

        return cleaned_data

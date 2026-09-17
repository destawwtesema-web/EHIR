
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import Facility, OrganizationUnit

from .forms import (
    FeedbackCreateForm,
    FeedbackReplyForm,
    FeedbackStatusForm,
)
from .models import Feedback


# ============================================================
# ROLE CONSTANTS
# ============================================================

ROLE_MINISTRY = "MINISTRY_ADMIN"
ROLE_REGION = "REGION_ADMIN"
ROLE_SUBCITY = "SUBCITY_ADMIN"
ROLE_FACILITY = "FACILITY_USER"


# ============================================================
# ORGANIZATION TYPES
# ============================================================

ORG_MINISTRY = OrganizationUnit.UnitType.MINISTRY
ORG_REGION = OrganizationUnit.UnitType.REGION
ORG_SUBCITY = OrganizationUnit.UnitType.SUBCITY
ORG_ZONE = OrganizationUnit.UnitType.ZONE
ORG_WOREDA = OrganizationUnit.UnitType.WOREDA

LOWER_ORG_TYPES = {
    ORG_SUBCITY,
    ORG_ZONE,
    ORG_WOREDA,
}


# ============================================================
# PROFILE
# ============================================================

def get_active_profile(request):
    """
    Return the active EHIRS profile for the logged-in user.
    """

    try:
        profile = request.user.profile

    except AttributeError:
        return None

    if not profile:
        return None

    if not profile.active:
        return None

    return profile


# ============================================================
# ORGANIZATION HELPERS
# ============================================================

def get_ministry_organization():
    """
    Return the active Ministry of Health organization.
    """

    return (
        OrganizationUnit.objects
        .filter(
            unit_type=ORG_MINISTRY,
            active=True,
        )
        .order_by("id")
        .first()
    )


def get_profile_organization(profile):
    """
    Return the effective organization for a profile.

    Ministry Admins may have organization=None.
    In that case the active Ministry organization is used.
    """

    if not profile:
        return None

    if profile.role == ROLE_MINISTRY:
        return (
            profile.organization
            or get_ministry_organization()
        )

    return profile.organization


def get_parent_region(organization):
    """
    Walk upward through the hierarchy and return
    the Region responsible for the organization.
    """

    if not organization:
        return None

    current = organization
    visited = set()

    while current and current.pk not in visited:

        if current.unit_type == ORG_REGION:
            return current

        visited.add(current.pk)
        current = current.parent

    return None


def organization_is_in_scope(
    organization,
    root_organization,
):
    """
    Return True when organization is the root organization
    or a descendant of the root organization.
    """

    if not organization or not root_organization:
        return False

    current = organization
    visited = set()

    while current and current.pk not in visited:

        if current.pk == root_organization.pk:
            return True

        visited.add(current.pk)
        current = current.parent

    return False


def get_descendant_organizations(organization):
    """
    Return the supplied organization and all active
    descendant organizations.
    """

    if not organization:
        return OrganizationUnit.objects.none()

    organization_ids = {organization.pk}
    pending = [organization.pk]

    while pending:

        child_ids = list(
            OrganizationUnit.objects
            .filter(
                parent_id__in=pending,
                active=True,
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

        new_ids = [
            child_id
            for child_id in child_ids
            if child_id not in organization_ids
        ]

        if not new_ids:
            break

        organization_ids.update(new_ids)
        pending = new_ids

    return (
        OrganizationUnit.objects
        .filter(
            pk__in=organization_ids,
            active=True,
        )
        .order_by("name")
    )


def get_facilities_under_organization(organization):
    """
    Return all active facilities belonging to an organization
    or any organization below it.
    """

    if not organization:
        return Facility.objects.none()

    organizations = get_descendant_organizations(
        organization
    )

    return (
        Facility.objects
        .filter(
            organization__in=organizations,
            active=True,
        )
        .select_related("organization")
        .order_by("name")
    )


# ============================================================
# CONVERSATION ROOT HELPER
# ============================================================

def get_feedback_root(feedback):
    """
    Return the original/root feedback.

    Original feedback:
        parent = None

    Reply:
        parent = original feedback
    """

    if not feedback:
        return None

    current = feedback
    visited = set()

    while current.parent_id:

        if current.pk in visited:
            break

        visited.add(current.pk)

        current = current.parent

        if not current:
            break

    return current


# ============================================================
# FEEDBACK QUERYSET
# ============================================================

def feedback_base_queryset():
    """
    Base queryset used throughout the Feedback application.
    """

    return (
        Feedback.objects
        .select_related(
            "sender",
            "sender_organization",
            "sender_facility",
            "recipient_organization",
            "recipient_facility",
            "resolved_by",
            "parent",
            "period",
        )
    )


# ============================================================
# ACCESS CONTROL
# ============================================================

def accessible_feedback(profile):
    """
    Return feedback records the current profile can access.

    Ministry:
        All feedback.

    Region:
        Feedback involving the Region, descendants,
        or facilities below the Region.

    Sub-city:
        Feedback involving the organization, its facilities,
        or communication with the parent Region.

    Facility:
        Feedback involving the exact facility.
    """

    if not profile:
        return Feedback.objects.none()

    queryset = feedback_base_queryset()

    # --------------------------------------------------------
    # MINISTRY
    # --------------------------------------------------------

    if profile.role == ROLE_MINISTRY:
        return queryset

    # --------------------------------------------------------
    # FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_FACILITY:

        facility = profile.facility

        if not facility:
            return Feedback.objects.none()

        return (
            queryset
            .filter(
                Q(sender_facility_id=facility.pk)
                | Q(recipient_facility_id=facility.pk)
            )
            .distinct()
        )

    # --------------------------------------------------------
    # ORGANIZATIONAL USERS
    # --------------------------------------------------------

    organization = get_profile_organization(profile)

    if not organization:
        return Feedback.objects.none()

    descendants = get_descendant_organizations(
        organization
    )

    facilities = Facility.objects.filter(
        organization__in=descendants,
        active=True,
    )

    scope_query = (
        Q(sender_organization__in=descendants)
        | Q(recipient_organization__in=descendants)
        | Q(sender_facility__in=facilities)
        | Q(recipient_facility__in=facilities)
    )

    # Lower organization can communicate with its Region.
    if profile.role == ROLE_SUBCITY:

        parent_region = get_parent_region(
            organization
        )

        if parent_region:

            scope_query |= (
                Q(sender_organization=parent_region)
                | Q(recipient_organization=parent_region)
            )

    return queryset.filter(
        scope_query
    ).distinct()


# ============================================================
# ENDPOINT MATCHING
# ============================================================

def profile_matches_sender(profile, feedback):
    """
    Check whether the profile represents the sender.
    """

    if not profile or not feedback:
        return False

    if feedback.sender_level == Feedback.SenderLevel.FACILITY:

        return (
            profile.role == ROLE_FACILITY
            and profile.facility_id
            == feedback.sender_facility_id
        )

    if profile.role == ROLE_FACILITY:
        return False

    organization = get_profile_organization(
        profile
    )

    return (
        organization is not None
        and organization.pk
        == feedback.sender_organization_id
    )


def profile_matches_recipient(profile, feedback):
    """
    Check whether the profile represents the recipient.
    """

    if not profile or not feedback:
        return False

    if (
        feedback.recipient_level
        == Feedback.RecipientLevel.FACILITY
    ):

        return (
            profile.role == ROLE_FACILITY
            and profile.facility_id
            == feedback.recipient_facility_id
        )

    if profile.role == ROLE_FACILITY:
        return False

    organization = get_profile_organization(
        profile
    )

    return (
        organization is not None
        and organization.pk
        == feedback.recipient_organization_id
    )


# ============================================================
# CONVERSATION PERMISSIONS
# ============================================================

def can_reply_to_feedback(profile, feedback):
    """
    Only the original sender or recipient endpoint
    can reply.
    """

    if not profile or not feedback:
        return False

    root = get_feedback_root(feedback)

    if not root:
        return False

    return (
        profile_matches_sender(profile, root)
        or profile_matches_recipient(profile, root)
    )


def can_manage_feedback(profile, feedback):
    """
    Only the recipient organization can manage status.

    Facility users cannot change feedback status.
    """

    if not profile or not feedback:
        return False

    if profile.role == ROLE_FACILITY:
        return False

    root = get_feedback_root(feedback)

    if not root:
        return False

    return profile_matches_recipient(
        profile,
        root,
    )


# ============================================================
# SENDER INFORMATION
# ============================================================

def get_sender_information(profile):
    """
    Determine the sender endpoint automatically from
    the logged-in user's EHIRS profile.
    """

    if not profile:
        raise ValueError(
            "Your EHIRS profile could not be found."
        )

    # --------------------------------------------------------
    # FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_FACILITY:

        facility = profile.facility

        if not facility:
            raise ValueError(
                "Your account is not linked to a facility."
            )

        if not facility.active:
            raise ValueError(
                "Your facility is inactive."
            )

        if not facility.organization:
            raise ValueError(
                "Your facility is not linked to an organization."
            )

        return {
            "level": Feedback.SenderLevel.FACILITY,
            "organization": facility.organization,
            "facility": facility,
        }

    # --------------------------------------------------------
    # SUBCITY / ZONE / WOREDA
    # --------------------------------------------------------

    if profile.role == ROLE_SUBCITY:

        organization = profile.organization

        if not organization:
            raise ValueError(
                "Your account is not linked to an organization."
            )

        if not organization.active:
            raise ValueError(
                "Your organization is inactive."
            )

        if organization.unit_type not in LOWER_ORG_TYPES:
            raise ValueError(
                "Your organization must be a "
                "Sub-city, Zone or Woreda."
            )

        return {
            "level": Feedback.SenderLevel.SUBCITY,
            "organization": organization,
            "facility": None,
        }

    # --------------------------------------------------------
    # REGION
    # --------------------------------------------------------

    if profile.role == ROLE_REGION:

        organization = profile.organization

        if not organization:
            raise ValueError(
                "Your account is not linked to a Region."
            )

        if organization.unit_type != ORG_REGION:
            raise ValueError(
                "Your account organization is not configured "
                "as a Region."
            )

        return {
            "level": Feedback.SenderLevel.REGION,
            "organization": organization,
            "facility": None,
        }

    # --------------------------------------------------------
    # MINISTRY
    # --------------------------------------------------------

    if profile.role == ROLE_MINISTRY:

        organization = get_profile_organization(
            profile
        )

        if not organization:
            raise ValueError(
                "The Ministry of Health organization "
                "has not been configured."
            )

        if organization.unit_type != ORG_MINISTRY:
            raise ValueError(
                "The Ministry account is not linked "
                "to a Ministry organization."
            )

        return {
            "level": Feedback.SenderLevel.MINISTRY,
            "organization": organization,
            "facility": None,
        }

    raise ValueError(
        "Your account role is not configured for Feedback."
    )


# ============================================================
# RECEIVER CHOICES
# ============================================================

def get_receiver_choices(profile):
    """
    Generate authorized receiver choices for the
    current user.
    """

    choices = [
        ("", "Select receiver...")
    ]

    if not profile:
        return choices

    # --------------------------------------------------------
    # FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_FACILITY:

        facility = profile.facility

        if not facility or not facility.organization:
            return choices

        organization = facility.organization

        if organization.unit_type in LOWER_ORG_TYPES:

            choices.append(
                (
                    f"org:{organization.pk}",
                    (
                        f"{organization.name} — "
                        f"{organization.get_unit_type_display()}"
                    ),
                )
            )

        return choices

    # --------------------------------------------------------
    # SUBCITY / ZONE / WOREDA
    # --------------------------------------------------------

    if profile.role == ROLE_SUBCITY:

        organization = profile.organization

        if not organization:
            return choices

        region = get_parent_region(
            organization
        )

        if region:

            choices.append(
                (
                    f"org:{region.pk}",
                    f"{region.name} — Region",
                )
            )

        facilities = (
            Facility.objects
            .filter(
                organization=organization,
                active=True,
            )
            .order_by("name")
        )

        for facility in facilities:

            choices.append(
                (
                    f"facility:{facility.pk}",
                    f"{facility.name} — Facility",
                )
            )

        return choices

    # --------------------------------------------------------
    # REGION
    # --------------------------------------------------------

    if profile.role == ROLE_REGION:

        region = profile.organization

        if not region:
            return choices

        ministry = get_ministry_organization()

        if ministry:

            choices.append(
                (
                    f"org:{ministry.pk}",
                    f"{ministry.name} — Ministry",
                )
            )

        organizations = (
            get_descendant_organizations(region)
            .exclude(pk=region.pk)
            .filter(
                unit_type__in=list(LOWER_ORG_TYPES)
            )
            .order_by("name")
        )

        for organization in organizations:

            choices.append(
                (
                    f"org:{organization.pk}",
                    (
                        f"{organization.name} — "
                        f"{organization.get_unit_type_display()}"
                    ),
                )
            )

        facilities = get_facilities_under_organization(
            region
        )

        for facility in facilities:

            choices.append(
                (
                    f"facility:{facility.pk}",
                    f"{facility.name} — Facility",
                )
            )

        return choices

    # --------------------------------------------------------
    # MINISTRY
    # --------------------------------------------------------

    if profile.role == ROLE_MINISTRY:

        regions = (
            OrganizationUnit.objects
            .filter(
                unit_type=ORG_REGION,
                active=True,
            )
            .order_by("name")
        )

        for region in regions:

            choices.append(
                (
                    f"org:{region.pk}",
                    f"{region.name} — Region",
                )
            )

        return choices

    return choices


# ============================================================
# RECEIVER PARSER
# ============================================================

def get_selected_receiver(
    selected_value,
    profile,
):
    """
    Convert a receiver choice into a validated receiver.

    Expected values:

        org:<id>
        facility:<id>
    """

    if not selected_value:
        raise ValueError(
            "Please select a receiver."
        )

    try:

        receiver_type, receiver_id = (
            selected_value.split(":", 1)
        )

        receiver_id = int(receiver_id)

    except (
        ValueError,
        AttributeError,
    ):

        raise ValueError(
            "The selected receiver is invalid."
        )

    if receiver_type == "org":

        organization = get_object_or_404(
            OrganizationUnit,
            pk=receiver_id,
            active=True,
        )

        return validate_organization_receiver(
            organization,
            profile,
        )

    if receiver_type == "facility":

        facility = get_object_or_404(
            Facility.objects.select_related(
                "organization"
            ),
            pk=receiver_id,
            active=True,
        )

        return validate_facility_receiver(
            facility,
            profile,
        )

    raise ValueError(
        "The selected receiver type is invalid."
    )


# ============================================================
# VALIDATE ORGANIZATION RECEIVER
# ============================================================

def validate_organization_receiver(
    organization,
    profile,
):
    """
    Validate an organization receiver according to
    the sender's role.
    """

    role = profile.role

    # --------------------------------------------------------
    # FACILITY -> ORGANIZATION
    # --------------------------------------------------------

    if role == ROLE_FACILITY:

        facility = profile.facility

        if not facility:
            raise ValueError(
                "Your facility could not be determined."
            )

        sender_organization = facility.organization

        if not sender_organization:
            raise ValueError(
                "Your facility has no reporting organization."
            )

        if organization.pk == sender_organization.pk:

            if organization.unit_type not in LOWER_ORG_TYPES:
                raise ValueError(
                    "The selected organization is not a valid "
                    "Sub-city/Woreda/Zone reporting unit."
                )

            return {
                "level": Feedback.RecipientLevel.SUBCITY,
                "organization": organization,
                "facility": None,
            }

        raise ValueError(
            "Health Centers can only send feedback directly "
            "to their Sub-city/Woreda/Zone, not to Region or Ministry."
        )

    # --------------------------------------------------------
    # LOWER ORGANIZATION -> REGION
    # --------------------------------------------------------

    if role == ROLE_SUBCITY:

        sender_organization = profile.organization

        if not sender_organization:
            raise ValueError(
                "Your organization could not be determined."
            )

        parent_region = get_parent_region(
            sender_organization
        )

        if not parent_region:
            raise ValueError(
                "Your parent Region could not be determined."
            )

        if organization.pk != parent_region.pk:

            raise ValueError(
                "You can only send organizational feedback "
                "to your parent Region."
            )

        return {
            "level": Feedback.RecipientLevel.REGION,
            "organization": organization,
            "facility": None,
        }

    # --------------------------------------------------------
    # REGION
    # --------------------------------------------------------

    if role == ROLE_REGION:

        region = profile.organization

        if not region:
            raise ValueError(
                "Your Region could not be determined."
            )

        # Region -> Ministry
        ministry = get_ministry_organization()

        if ministry and organization.pk == ministry.pk:

            return {
                "level": Feedback.RecipientLevel.MINISTRY,
                "organization": organization,
                "facility": None,
            }

        # Region -> lower organization
        if organization.unit_type in LOWER_ORG_TYPES:

            if not organization_is_in_scope(
                organization,
                region,
            ):

                raise ValueError(
                    "The selected organization does not "
                    "belong to your Region."
                )

            return {
                "level": Feedback.RecipientLevel.SUBCITY,
                "organization": organization,
                "facility": None,
            }

        raise ValueError(
            "The selected organization is not a valid "
            "receiver for your Region."
        )

    # --------------------------------------------------------
    # MINISTRY -> REGION
    # --------------------------------------------------------

    if role == ROLE_MINISTRY:

        if organization.unit_type != ORG_REGION:

            raise ValueError(
                "Ministry users can send organizational "
                "feedback only to a Region."
            )

        return {
            "level": Feedback.RecipientLevel.REGION,
            "organization": organization,
            "facility": None,
        }

    raise ValueError(
        "Your account role cannot send feedback "
        "to this organization."
    )


# ============================================================
# VALIDATE FACILITY RECEIVER
# ============================================================

def validate_facility_receiver(
    facility,
    profile,
):
    """
    Validate a facility receiver.

    Allowed:

        Lower organization -> Facility
        Region -> Facility

    Not allowed:

        Facility -> Facility
        Ministry -> Facility
    """

    if not facility.organization:
        raise ValueError(
            "The selected facility has no organization."
        )

    # --------------------------------------------------------
    # FACILITY -> FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_FACILITY:

        raise ValueError(
            "Facilities cannot directly send feedback "
            "to another facility."
        )

    # --------------------------------------------------------
    # LOWER ORGANIZATION -> FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_SUBCITY:

        organization = profile.organization

        if not organization:
            raise ValueError(
                "Your organization could not be determined."
            )

        if facility.organization_id != organization.pk:

            raise ValueError(
                "You can only send feedback to facilities "
                "under your organization."
            )

        return {
            "level": Feedback.RecipientLevel.FACILITY,
            "organization": facility.organization,
            "facility": facility,
        }

    # --------------------------------------------------------
    # REGION -> FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_REGION:

        region = profile.organization

        if not region:
            raise ValueError(
                "Your Region could not be determined."
            )

        if not organization_is_in_scope(
            facility.organization,
            region,
        ):

            raise ValueError(
                "The selected facility does not belong "
                "to your Region."
            )

        return {
            "level": Feedback.RecipientLevel.FACILITY,
            "organization": facility.organization,
            "facility": facility,
        }

    # --------------------------------------------------------
    # MINISTRY -> FACILITY
    # --------------------------------------------------------

    if profile.role == ROLE_MINISTRY:

        raise ValueError(
            "Ministry users should communicate "
            "through the Region level."
        )

    raise ValueError(
        "Your account role cannot send feedback "
        "to this facility."
    )


# ============================================================
# PREPARE NEW FEEDBACK
# ============================================================

def prepare_new_feedback(
    feedback,
    profile,
    selected_receiver,
):
    """
    Populate sender and receiver fields automatically.
    """

    sender = get_sender_information(
        profile
    )

    receiver = get_selected_receiver(
        selected_receiver,
        profile,
    )

    feedback.sender_level = sender["level"]
    feedback.sender_organization = (
        sender["organization"]
    )
    feedback.sender_facility = (
        sender["facility"]
    )

    feedback.recipient_level = receiver["level"]
    feedback.recipient_organization = (
        receiver["organization"]
    )
    feedback.recipient_facility = (
        receiver["facility"]
    )


# ============================================================
# PREPARE REPLY
# ============================================================

def prepare_reply_routing(
    feedback,
    profile,
):
    """
    Route a reply to the other endpoint of the
    original conversation.
    """

    sender = get_sender_information(
        profile
    )

    root = get_feedback_root(feedback)

    if not root:
        raise ValueError(
            "The original feedback conversation could not be found."
        )

    is_sender = profile_matches_sender(
        profile,
        root,
    )

    is_recipient = profile_matches_recipient(
        profile,
        root,
    )

    if not (is_sender or is_recipient):

        raise PermissionError(
            "You are not a participant in this feedback conversation."
        )

    feedback.sender_level = sender["level"]
    feedback.sender_organization = (
        sender["organization"]
    )
    feedback.sender_facility = (
        sender["facility"]
    )

    if is_sender:

        feedback.recipient_level = (
            root.recipient_level
        )

        feedback.recipient_organization = (
            root.recipient_organization
        )

        feedback.recipient_facility = (
            root.recipient_facility
        )

    else:

        feedback.recipient_level = (
            root.sender_level
        )

        feedback.recipient_organization = (
            root.sender_organization
        )

        feedback.recipient_facility = (
            root.sender_facility
        )

    # Replies stay in the same reporting period.
    if hasattr(feedback, "period"):
        feedback.period = root.period


# ============================================================
# SIMPLE FEEDBACK DASHBOARD
# ============================================================

@login_required
def feedback_dashboard(request):
    """
    Simple Feedback Dashboard.

    The dashboard contains ONLY:

        1. Sent Messages
        2. Received Messages
        3. Unseen Messages
        4. Organization Unit filter
        5. Year filter
        6. Month filter
        7. Message list

    No status/category/priority/flow/search/level/
    reporting-period filters are used here.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your EHIRS profile is missing or inactive.",
        )

        return redirect("accounts:login")

    # ========================================================
    # ACCESSIBLE FEEDBACK
    # ========================================================

    queryset = accessible_feedback(profile)

    # ========================================================
    # DETERMINE USER'S SENDER / RECEIVER ENDPOINT
    # ========================================================

    if profile.role == ROLE_FACILITY:

        facility = profile.facility

        if not facility:

            messages.error(
                request,
                "Your account is not linked to a facility.",
            )

            return redirect("accounts:login")

        sent_condition = Q(
            sender_facility_id=facility.pk
        )

        received_condition = Q(
            recipient_facility_id=facility.pk
        )

    else:

        organization = get_profile_organization(
            profile
        )

        if not organization:

            messages.error(
                request,
                "Your account is not linked to an organization.",
            )

            return redirect("accounts:login")

        sent_condition = Q(
            sender_organization_id=organization.pk
        )

        received_condition = Q(
            recipient_organization_id=organization.pk
        )

    # ========================================================
    # ORGANIZATION UNIT FILTER
    # ========================================================

    organization_filter = (
        request.GET.get(
            "organization",
            "",
        ).strip()
    )

    if organization_filter:

        try:

            organization_id = int(
                organization_filter
            )

            # Only messages involving the selected
            # organization are displayed.

            queryset = queryset.filter(
                Q(
                    sender_organization_id=organization_id
                )
                |
                Q(
                    recipient_organization_id=organization_id
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            organization_filter = ""

    # ========================================================
    # YEAR FILTER
    # ========================================================

    selected_year = (
        request.GET.get(
            "year",
            "",
        ).strip()
    )

    if selected_year:

        try:

            year_number = int(
                selected_year
            )

            if 1900 <= year_number <= 2100:

                queryset = queryset.filter(
                    created_at__year=year_number
                )

            else:

                selected_year = ""

        except (
            TypeError,
            ValueError,
        ):

            selected_year = ""

    # ========================================================
    # MONTH FILTER
    # ========================================================

    selected_month = (
        request.GET.get(
            "month",
            "",
        ).strip()
    )

    if selected_month:

        try:

            month_number = int(
                selected_month
            )

            if 1 <= month_number <= 12:

                queryset = queryset.filter(
                    created_at__month=month_number
                )

            else:

                selected_month = ""

        except (
            TypeError,
            ValueError,
        ):

            selected_month = ""

    # ========================================================
    # SENT COUNT
    # ========================================================

    sent_count = (
        queryset
        .filter(sent_condition)
        .count()
    )

    # ========================================================
    # RECEIVED COUNT
    # ========================================================

    received_count = (
        queryset
        .filter(received_condition)
        .count()
    )

    # ========================================================
    # UNSEEN COUNT
    # ========================================================

    unread_count = (
        queryset
        .filter(received_condition)
        .filter(read_at__isnull=True)
        .count()
    )

    # ========================================================
    # MESSAGE LIST
    # ========================================================

    feedback_list = list(
        queryset
        .order_by("-created_at")
    )

    # ========================================================
    # IDENTIFY RECEIVED MESSAGES
    # ========================================================

    current_organization = None

    if profile.role != ROLE_FACILITY:

        current_organization = (
            get_profile_organization(profile)
        )

    for feedback in feedback_list:

        if profile.role == ROLE_FACILITY:

            feedback.is_received = (
                feedback.recipient_facility_id
                == profile.facility_id
            )

        else:

            feedback.is_received = (
                current_organization is not None
                and
                feedback.recipient_organization_id
                == current_organization.pk
            )

    # ========================================================
    # ORGANIZATION OPTIONS
    #
    # Only organizations that occur in the user's
    # accessible feedback are shown.
    # ========================================================

    organization_ids = set()

    for feedback in feedback_list:

        if feedback.sender_organization_id:

            organization_ids.add(
                feedback.sender_organization_id
            )

        if feedback.recipient_organization_id:

            organization_ids.add(
                feedback.recipient_organization_id
            )

    # Also include organizations from all accessible
    # feedback when a filter is not selected.

    accessible_organization_ids = set(
        accessible_feedback(profile)
        .filter(
            sender_organization__isnull=False
        )
        .values_list(
            "sender_organization_id",
            flat=True,
        )
    )

    accessible_recipient_ids = set(
        accessible_feedback(profile)
        .filter(
            recipient_organization__isnull=False
        )
        .values_list(
            "recipient_organization_id",
            flat=True,
        )
    )

    organization_ids.update(
        accessible_organization_ids
    )

    organization_ids.update(
        accessible_recipient_ids
    )

    organization_options = (
        OrganizationUnit.objects
        .filter(
            pk__in=organization_ids,
            active=True,
        )
        .order_by("name")
    )

    # ========================================================
    # YEAR OPTIONS
    # ========================================================

    now = timezone.now()

    accessible_dates = (
        accessible_feedback(profile)
        .exclude(
            created_at__isnull=True
        )
        .dates(
            "created_at",
            "year",
            order="DESC",
        )
    )

    year_values = sorted(
        {
            date_value.year
            for date_value in accessible_dates
        },
        reverse=True,
    )

    if now.year not in year_values:

        year_values.insert(
            0,
            now.year,
        )

    year_choices = year_values

    # ========================================================
    # MONTH OPTIONS
    # ========================================================

    month_choices = [
        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),
        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),
    ]

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {
        "profile": profile,

        "feedback_list": feedback_list,

        # Three dashboard cards
        "sent_count": sent_count,
        "received_count": received_count,
        "unread_count": unread_count,

        # Organization filter
        "organization_options": organization_options,
        "organization_filter": organization_filter,

        # Year filter
        "year_choices": year_choices,
        "selected_year": selected_year,

        # Month filter
        "month_choices": month_choices,
        "selected_month": selected_month,
    }

    return render(
        request,
        "feedback/dashboard.html",
        context,
    )


# ============================================================
# CREATE FEEDBACK
# ============================================================

@login_required
def feedback_create(request):

    profile = get_active_profile(
        request
    )

    if not profile:

        messages.error(
            request,
            "Your EHIRS profile is missing or inactive.",
        )

        return redirect(
            "accounts:login"
        )

    try:

        sender = get_sender_information(
            profile
        )

    except ValueError as exc:

        messages.error(
            request,
            str(exc),
        )

        return redirect(
            "feedback:dashboard"
        )

    recipient_choices = get_receiver_choices(
        profile
    )

    if request.method == "POST":

        form = FeedbackCreateForm(
            request.POST,
            recipient_choices=recipient_choices,
        )

        if form.is_valid():

            try:

                with transaction.atomic():

                    feedback = form.save(
                        commit=False
                    )

                    feedback.sender = request.user

                    prepare_new_feedback(
                        feedback,
                        profile,
                        form.cleaned_data["recipient"],
                    )

                    feedback.status = (
                        Feedback.Status.PENDING
                    )

                    feedback.save()

                messages.success(
                    request,
                    "Feedback was submitted successfully.",
                )

                return redirect(
                    "feedback:detail",
                    feedback_id=feedback.pk,
                )

            except (
                ValueError,
                PermissionError,
                ValidationError,
            ) as exc:

                messages.error(
                    request,
                    str(exc),
                )

            except Exception:

                messages.error(
                    request,
                    "The feedback could not be submitted. "
                    "Please check the selected receiver and try again.",
                )

    else:

        form = FeedbackCreateForm(
            recipient_choices=recipient_choices
        )

    context = {
        "profile": profile,
        "sender": sender,
        "form": form,
        "recipient_choices": recipient_choices,
    }

    return render(
        request,
        "feedback/create.html",
        context,
    )


# ============================================================
# FEEDBACK DETAIL
# ============================================================

@login_required
def feedback_detail(
    request,
    feedback_id,
):

    profile = get_active_profile(
        request
    )

    if not profile:

        messages.error(
            request,
            "Your EHIRS profile is missing or inactive.",
        )

        return redirect(
            "accounts:login"
        )

    visible_feedback = accessible_feedback(
        profile
    )

    feedback = get_object_or_404(
        visible_feedback,
        pk=feedback_id,
    )

    # --------------------------------------------------------
    # GET ROOT
    # --------------------------------------------------------

    root = get_feedback_root(
        feedback
    )

    if not root:

        messages.error(
            request,
            "The original feedback conversation could not be found.",
        )

        return redirect(
            "feedback:dashboard"
        )

    if not visible_feedback.filter(
        pk=root.pk
    ).exists():

        messages.error(
            request,
            "You are not allowed to view this conversation.",
        )

        return redirect(
            "feedback:dashboard"
        )

    # --------------------------------------------------------
    # MARK AS READ
    # --------------------------------------------------------

    if (
        feedback.sender_id != request.user.pk
        and feedback.read_at is None
    ):

        feedback.read_at = timezone.now()

        feedback.save(
            update_fields=[
                "read_at",
            ]
        )

    # --------------------------------------------------------
    # CONVERSATION
    # --------------------------------------------------------

    conversation = (
        feedback_base_queryset()
        .filter(
            Q(pk=root.pk)
            | Q(parent=root)
        )
        .order_by("created_at")
    )

    can_reply = can_reply_to_feedback(
        profile,
        root,
    )

    can_manage = can_manage_feedback(
        profile,
        root,
    )

    context = {
        "profile": profile,
        "feedback": feedback,
        "root": root,
        "conversation": conversation,

        "can_reply": can_reply,
        "can_manage": can_manage,

        "reply_form": FeedbackReplyForm(),

        "status_form": FeedbackStatusForm(
            initial={
                "status": root.status,
                "resolution_note": (
                    root.resolution_note or ""
                ),
            }
        ),
    }

    return render(
        request,
        "feedback/detail.html",
        context,
    )


# ============================================================
# REPLY
# ============================================================

@login_required
def feedback_reply(
    request,
    feedback_id,
):

    if request.method != "POST":

        return redirect(
            "feedback:detail",
            feedback_id=feedback_id,
        )

    profile = get_active_profile(
        request
    )

    if not profile:

        messages.error(
            request,
            "Your EHIRS profile is missing or inactive.",
        )

        return redirect(
            "accounts:login"
        )

    visible_feedback = accessible_feedback(
        profile
    )

    feedback = get_object_or_404(
        visible_feedback,
        pk=feedback_id,
    )

    # --------------------------------------------------------
    # ROOT
    # --------------------------------------------------------

    root = get_feedback_root(
        feedback
    )

    if not root:

        messages.error(
            request,
            "The original feedback conversation could not be found.",
        )

        return redirect(
            "feedback:dashboard"
        )

    # --------------------------------------------------------
    # PERMISSION
    # --------------------------------------------------------

    if not can_reply_to_feedback(
        profile,
        root,
    ):

        messages.error(
            request,
            "You are not allowed to reply to this feedback.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # --------------------------------------------------------
    # CLOSED
    # --------------------------------------------------------

    if root.status == Feedback.Status.CLOSED:

        messages.error(
            request,
            "This feedback conversation is closed.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # --------------------------------------------------------
    # FORM
    # --------------------------------------------------------

    form = FeedbackReplyForm(
        request.POST
    )

    if not form.is_valid():

        messages.error(
            request,
            "Please enter a valid reply.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # --------------------------------------------------------
    # SAVE REPLY
    # --------------------------------------------------------

    try:

        with transaction.atomic():

            reply = Feedback()

            reply.sender = request.user
            reply.parent = root

            if root.subject.startswith("Re:"):

                reply.subject = root.subject

            else:

                reply.subject = (
                    f"Re: {root.subject}"
                )

            reply.category = root.category
            reply.priority = root.priority
            reply.message = (
                form.cleaned_data["message"]
            )

            # Same reporting period as original.
            if hasattr(reply, "period"):

                reply.period = root.period

            prepare_reply_routing(
                reply,
                profile,
            )

            reply.status = root.status

            reply.save()

            # ------------------------------------------------
            # PENDING / UNDER REVIEW -> IN PROGRESS
            # ------------------------------------------------

            if root.status in (
                Feedback.Status.PENDING,
                Feedback.Status.UNDER_REVIEW,
            ):

                root.status = (
                    Feedback.Status.IN_PROGRESS
                )

                root.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            # ------------------------------------------------
            # RESOLVED -> IN PROGRESS
            # ------------------------------------------------

            elif root.status == Feedback.Status.RESOLVED:

                root.status = (
                    Feedback.Status.IN_PROGRESS
                )

                root.resolution_note = ""
                root.resolved_by = None
                root.resolved_at = None

                root.save(
                    update_fields=[
                        "status",
                        "resolution_note",
                        "resolved_by",
                        "resolved_at",
                        "updated_at",
                    ]
                )

        messages.success(
            request,
            "Your reply was sent successfully.",
        )

    except (
        ValueError,
        PermissionError,
        ValidationError,
    ) as exc:

        messages.error(
            request,
            str(exc),
        )

    except Exception:

        messages.error(
            request,
            "The reply could not be sent. Please try again.",
        )

    return redirect(
        "feedback:detail",
        feedback_id=root.pk,
    )


# ============================================================
# UPDATE STATUS
# ============================================================

@login_required
def feedback_update_status(
    request,
    feedback_id,
):

    if request.method != "POST":

        return redirect(
            "feedback:detail",
            feedback_id=feedback_id,
        )

    profile = get_active_profile(
        request
    )

    if not profile:

        messages.error(
            request,
            "Your EHIRS profile is missing or inactive.",
        )

        return redirect(
            "accounts:login"
        )

    visible_feedback = accessible_feedback(
        profile
    )

    feedback = get_object_or_404(
        visible_feedback,
        pk=feedback_id,
    )

    # --------------------------------------------------------
    # ROOT
    # --------------------------------------------------------

    root = get_feedback_root(
        feedback
    )

    if not root:

        messages.error(
            request,
            "The original feedback conversation could not be found.",
        )

        return redirect(
            "feedback:dashboard"
        )

    # --------------------------------------------------------
    # PERMISSION
    # --------------------------------------------------------

    if not can_manage_feedback(
        profile,
        root,
    ):

        messages.error(
            request,
            "You are not authorized to manage this feedback.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # --------------------------------------------------------
    # CLOSED
    # --------------------------------------------------------

    if root.status == Feedback.Status.CLOSED:

        messages.error(
            request,
            "This feedback is already closed.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # --------------------------------------------------------
    # FORM
    # --------------------------------------------------------

    form = FeedbackStatusForm(
        request.POST
    )

    if not form.is_valid():

        messages.error(
            request,
            "Please select a valid status.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    new_status = form.cleaned_data[
        "status"
    ]

    resolution_note = (
        form.cleaned_data.get(
            "resolution_note"
        )
        or ""
    ).strip()

    current_status = root.status

    # ========================================================
    # ALLOWED STATUS TRANSITIONS
    # ========================================================

    allowed_transitions = {

        Feedback.Status.PENDING: {
            Feedback.Status.PENDING,
            Feedback.Status.UNDER_REVIEW,
            Feedback.Status.IN_PROGRESS,
            Feedback.Status.RESOLVED,
        },

        Feedback.Status.UNDER_REVIEW: {
            Feedback.Status.UNDER_REVIEW,
            Feedback.Status.IN_PROGRESS,
            Feedback.Status.RESOLVED,
        },

        Feedback.Status.IN_PROGRESS: {
            Feedback.Status.IN_PROGRESS,
            Feedback.Status.RESOLVED,
        },

        Feedback.Status.RESOLVED: {
            Feedback.Status.RESOLVED,
            Feedback.Status.CLOSED,
        },

        Feedback.Status.CLOSED: {
            Feedback.Status.CLOSED,
        },
    }

    allowed = allowed_transitions.get(
        current_status,
        set(),
    )

    if new_status not in allowed:

        messages.error(
            request,
            "This status transition is not allowed.",
        )

        return redirect(
            "feedback:detail",
            feedback_id=root.pk,
        )

    # ========================================================
    # RESOLUTION NOTE
    # ========================================================

    if new_status in (
        Feedback.Status.RESOLVED,
        Feedback.Status.CLOSED,
    ):

        if not resolution_note:

            if not root.resolution_note:

                messages.error(
                    request,
                    "A resolution note is required "
                    "when resolving or closing feedback.",
                )

                return redirect(
                    "feedback:detail",
                    feedback_id=root.pk,
                )

            resolution_note = (
                root.resolution_note
            )

    # ========================================================
    # SAVE STATUS
    # ========================================================

    try:

        with transaction.atomic():

            root.status = new_status

            # ------------------------------------------------
            # RESOLVED / CLOSED
            # ------------------------------------------------

            if new_status in (
                Feedback.Status.RESOLVED,
                Feedback.Status.CLOSED,
            ):

                root.resolution_note = (
                    resolution_note
                )

                root.resolved_by = request.user

                if root.resolved_at is None:

                    root.resolved_at = timezone.now()

            # ------------------------------------------------
            # ACTIVE STATUS
            # ------------------------------------------------

            else:

                root.resolution_note = ""
                root.resolved_by = None
                root.resolved_at = None

            root.save()

        messages.success(
            request,
            "Feedback status was updated successfully.",
        )

    except ValidationError as exc:

        messages.error(
            request,
            str(exc),
        )

    except Exception:

        messages.error(
            request,
            "The feedback status could not be updated. "
            "Please try again.",
        )

    return redirect(
        "feedback:detail",
        feedback_id=root.pk,
    )
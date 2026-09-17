from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from assessments.models import Assessment
from lqas.models import LQASAssessment


# ================================================================
# GET ACTIVE USER PROFILE
# ================================================================

def get_profile(request):

    profile = getattr(
        request.user,
        "profile",
        None,
    )

    if not profile:
        return None

    if not profile.active:
        return None

    return profile


# ================================================================
# CALCULATE ONE ASSESSMENT SCORE
# ================================================================

def calculate_assessment_score(assessment):

    section_totals = {}

    responses = (
        assessment.responses
        .select_related(
            "indicator",
            "indicator__thematic_area",
            "indicator__thematic_area__section",
        )
    )

    for response in responses:

        indicator = response.indicator
        thematic_area = indicator.thematic_area
        section = thematic_area.section

        section_code = section.code.upper()

        if section_code not in section_totals:

            section_totals[section_code] = {
                "achieved": Decimal("0.00"),
                "maximum": Decimal("0.00"),
                "weight": Decimal(section.weight or 0),
            }

        section_totals[
            section_code
        ]["achieved"] += (
            response.calculated_score
            or Decimal("0.00")
        )

        section_totals[
            section_code
        ]["maximum"] += (
            indicator.maximum_score
            or Decimal("0.00")
        )

    section_scores = {}

    for section_code, data in section_totals.items():

        achieved = data["achieved"]
        maximum = data["maximum"]
        weight = data["weight"]

        if maximum > 0:

            percentage = (
                achieved
                / maximum
            ) * Decimal("100")

        else:

            percentage = Decimal("0.00")

        weighted_score = (
            percentage
            / Decimal("100")
        ) * weight

        section_scores[
            section_code
        ] = weighted_score.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    section_a = section_scores.get(
        "A",
        Decimal("0.00"),
    )

    section_b = section_scores.get(
        "B",
        Decimal("0.00"),
    )

    section_c = section_scores.get(
        "C",
        Decimal("0.00"),
    )

    overall = (
        section_a
        + section_b
        + section_c
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return {
        "A": section_a,
        "B": section_b,
        "C": section_c,
        "overall": overall,
    }


# ================================================================
# GET ROLE DASHBOARD URL
# ================================================================

def get_role_dashboard_url(profile):

    if profile.is_ministry_admin():

        return "dashboard:ministry"

    if profile.is_region_admin():

        return "dashboard:regional"

    if profile.is_subcity_admin():

        return "dashboard:subcity"

    if profile.is_facility_user():

        return "dashboard:facility"

    return "dashboard:home"


# ================================================================
# GET ROLE DASHBOARD NAME
# ================================================================

def get_role_dashboard_name(profile):

    if profile.is_ministry_admin():

        return "Ministry Dashboard"

    if profile.is_region_admin():

        return "Regional Dashboard"

    if profile.is_subcity_admin():

        return "Sub-city Dashboard"

    if profile.is_facility_user():

        return "Facility Dashboard"

    return "EHIRS Dashboard"


# ================================================================
# DASHBOARD DATA
# ================================================================

def dashboard_data(facilities):

    facilities = facilities.distinct()

    # ============================================================
    # ASSESSMENTS
    # ============================================================

    assessments = list(
        Assessment.objects
        .filter(
            facility__in=facilities
        )
        .select_related(
            "facility",
            "facility__organization",
            "period",
        )
        .prefetch_related(
            "responses__indicator__thematic_area__section"
        )
    )

    total_assessments = len(
        assessments
    )

    total_overall = Decimal("0.00")

    total_a = Decimal("0.00")
    total_b = Decimal("0.00")
    total_c = Decimal("0.00")

    for assessment in assessments:

        scores = calculate_assessment_score(
            assessment
        )

        # Display calculated score without changing database.
        assessment.total_score = (
            scores["overall"]
        )

        total_overall += (
            scores["overall"]
        )

        total_a += scores["A"]
        total_b += scores["B"]
        total_c += scores["C"]

    # ============================================================
    # AVERAGE SCORES
    # ============================================================

    if total_assessments > 0:

        average_score = (
            total_overall
            / Decimal(total_assessments)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        section_a_score = (
            total_a
            / Decimal(total_assessments)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        section_b_score = (
            total_b
            / Decimal(total_assessments)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        section_c_score = (
            total_c
            / Decimal(total_assessments)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    else:

        average_score = Decimal("0.00")

        section_a_score = Decimal("0.00")
        section_b_score = Decimal("0.00")
        section_c_score = Decimal("0.00")

    # ============================================================
    # ASSESSMENT STATUS COUNTS
    # ============================================================

    submitted_assessments = sum(
        1
        for assessment in assessments
        if assessment.status == "SUBMITTED"
    )

    reviewed_assessments = sum(
        1
        for assessment in assessments
        if assessment.status == "REVIEWED"
    )

    approved_assessments = sum(
        1
        for assessment in assessments
        if assessment.status == "APPROVED"
    )

    draft_assessments = sum(
        1
        for assessment in assessments
        if assessment.status == "DRAFT"
    )

    returned_assessments = sum(
        1
        for assessment in assessments
        if assessment.status == "RETURNED"
    )

    # ============================================================
    # RECENT ASSESSMENTS
    # ============================================================

    recent_assessments = sorted(
        assessments,
        key=lambda assessment: (
            assessment.period.year,
            assessment.period.period_number,
            assessment.created_at,
        ),
        reverse=True,
    )[:10]

    # ============================================================
    # LQAS ASSESSMENTS
    # ============================================================

    lqas_assessments = list(
        LQASAssessment.objects
        .filter(
            facility__in=facilities
        )
        .select_related(
            "facility",
            "facility__organization",
        )
    )

    total_lqas = len(
        lqas_assessments
    )

    if total_lqas > 0:

        total_lqas_percentage = sum(
            (
                lqas.percentage
                or Decimal("0.00")
                for lqas in lqas_assessments
            ),
            Decimal("0.00"),
        )

        average_lqas = (
            total_lqas_percentage
            / Decimal(total_lqas)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    else:

        average_lqas = Decimal("0.00")

    # ============================================================
    # RECENT LQAS
    # ============================================================

    recent_lqas = sorted(
        lqas_assessments,
        key=lambda lqas: (
            lqas.year,
            lqas.created_at,
        ),
        reverse=True,
    )[:10]

    # ============================================================
    # RETURN DATA
    # ============================================================

    return {

        # Assessments

        "total_assessments":
            total_assessments,

        "average_score":
            average_score,

        "section_a_score":
            section_a_score,

        "section_b_score":
            section_b_score,

        "section_c_score":
            section_c_score,

        # Statuses

        "submitted_assessments":
            submitted_assessments,

        "reviewed_assessments":
            reviewed_assessments,

        "approved_assessments":
            approved_assessments,

        "draft_assessments":
            draft_assessments,

        "returned_assessments":
            returned_assessments,

        # LQAS

        "total_lqas":
            total_lqas,

        "average_lqas":
            average_lqas,

        # Recent records

        "recent_assessments":
            recent_assessments,

        "recent_lqas":
            recent_lqas,
    }


# ================================================================
# MAIN EHIRS HOME
# ================================================================

@login_required
def dashboard_home(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    organizations = (
        profile.accessible_organizations()
        .select_related(
            "parent"
        )
        .distinct()
    )

    facilities = (
        profile.accessible_facilities()
        .select_related(
            "organization"
        )
        .distinct()
    )

    context = {

        # User

        "profile":
            profile,

        # Organization scope

        "organizations":
            organizations,

        "facilities":
            facilities,

        "total_organizations":
            organizations.count(),

        "total_facilities":
            facilities.count(),

        # Role dashboard

        "role_dashboard_url":
            get_role_dashboard_url(
                profile
            ),

        "role_dashboard_name":
            get_role_dashboard_name(
                profile
            ),

        # Assessment + LQAS

        **dashboard_data(
            facilities
        ),
    }

    return render(
        request,
        "dashboard/home.html",
        context,
    )


# ================================================================
# MINISTRY DASHBOARD
# ================================================================

@login_required
def ministry_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    if not profile.is_ministry_admin():

        return redirect(
            "dashboard:home"
        )

    organizations = (
        profile.accessible_organizations()
        .select_related(
            "parent"
        )
        .distinct()
    )

    facilities = (
        profile.accessible_facilities()
        .select_related(
            "organization"
        )
        .distinct()
    )

    context = {

        "profile":
            profile,

        "organizations":
            organizations,

        "facilities":
            facilities,

        "total_organizations":
            organizations.count(),

        "total_facilities":
            facilities.count(),

        **dashboard_data(
            facilities
        ),
    }

    return render(
        request,
        "dashboard/ministry.html",
        context,
    )


# ================================================================
# REGIONAL DASHBOARD
# ================================================================

@login_required
def regional_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    if not profile.is_region_admin():

        return redirect(
            "dashboard:home"
        )

    organizations = (
        profile.accessible_organizations()
        .select_related(
            "parent"
        )
        .distinct()
    )

    facilities = (
        profile.accessible_facilities()
        .select_related(
            "organization"
        )
        .distinct()
    )

    context = {

        "profile":
            profile,

        "organizations":
            organizations,

        "facilities":
            facilities,

        "total_organizations":
            organizations.count(),

        "total_facilities":
            facilities.count(),

        **dashboard_data(
            facilities
        ),
    }

    return render(
        request,
        "dashboard/regional.html",
        context,
    )


# ================================================================
# SUB-CITY DASHBOARD
# ================================================================

@login_required
def subcity_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    if not profile.is_subcity_admin():

        return redirect(
            "dashboard:home"
        )

    organizations = (
        profile.accessible_organizations()
        .select_related(
            "parent"
        )
        .distinct()
    )

    facilities = (
        profile.accessible_facilities()
        .select_related(
            "organization"
        )
        .distinct()
    )

    context = {

        "profile":
            profile,

        "organizations":
            organizations,

        "facilities":
            facilities,

        "total_organizations":
            organizations.count(),

        "total_facilities":
            facilities.count(),

        **dashboard_data(
            facilities
        ),
    }

    return render(
        request,
        "dashboard/subcity.html",
        context,
    )


# ================================================================
# FACILITY DASHBOARD
# ================================================================

@login_required
def facility_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    if not profile.is_facility_user():

        return redirect(
            "dashboard:home"
        )

    if not profile.facility:

        return redirect(
            "dashboard:home"
        )

    facilities = (
        profile.accessible_facilities()
        .select_related(
            "organization"
        )
        .distinct()
    )

    context = {

        "profile":
            profile,

        "facility":
            profile.facility,

        "facilities":
            facilities,

        "total_facilities":
            facilities.count(),

        "total_organizations":
            1,

        **dashboard_data(
            facilities
        ),
    }

    return render(
        request,
        "dashboard/facility.html",
        context,
    )
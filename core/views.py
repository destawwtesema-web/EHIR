
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import redirect, render

from assessments.models import Assessment, AssessmentPeriod
from core.models import Facility
from lqas.models import LQASAssessment


# ============================================================
# PROFILE
# ============================================================

def get_profile(request):
    """
    Return the active EHIRS profile for the logged-in user.
    """

    try:
        profile = request.user.profile

        if not profile.active:
            return None

        return profile

    except Exception:
        return None


# ============================================================
# HOME
# ============================================================

def home(request):

    if not request.user.is_authenticated:
        return redirect("accounts:login")

    return redirect("dashboard:home")


# ============================================================
# SAFE DECIMAL
# ============================================================

def safe_score(value):

    if value is None:
        return Decimal("0.00")

    try:
        return Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    except Exception:
        return Decimal("0.00")


# ============================================================
# ASSESSMENT STATUS
# ============================================================

def assessment_status(name):

    if hasattr(Assessment, "Status"):

        if hasattr(Assessment.Status, name):

            return getattr(
                Assessment.Status,
                name,
            )

    return name


# ============================================================
# PERIOD TYPE LABEL
# ============================================================

def get_period_type_label(period_type):

    labels = {
        "MONTHLY": "Monthly",
        "QUARTERLY": "Quarterly",
        "BIANNUAL": "Biannual",
        "ANNUAL": "Annual",
    }

    return labels.get(
        period_type,
        str(period_type or "")
        .replace("_", " ")
        .title(),
    )


# ============================================================
# PERIOD NUMBER LABEL
# ============================================================

def get_period_number_label(period):

    if not period:
        return ""

    period_type = getattr(
        period,
        "period_type",
        "",
    )

    number = getattr(
        period,
        "period_number",
        None,
    )

    try:
        number = int(number)
    except (TypeError, ValueError):
        number = None

    if period_type == "MONTHLY":

        month_names = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]

        if number and 1 <= number <= 12:
            return month_names[number - 1]

    if period_type == "QUARTERLY":

        if number and 1 <= number <= 4:
            return f"Q{number}"

    if period_type == "BIANNUAL":

        if number == 1:
            return "H1"

        if number == 2:
            return "H2"

    if period_type == "ANNUAL":

        return "Annual"

    return ""


# ============================================================
# PERIOD MONTH INFORMATION
# ============================================================

def get_period_months(period):

    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    if not period:
        return []

    period_type = getattr(
        period,
        "period_type",
        "",
    )

    number = getattr(
        period,
        "period_number",
        None,
    )

    try:
        number = int(number)
    except (TypeError, ValueError):
        number = None

    if period_type == "MONTHLY":

        if number and 1 <= number <= 12:
            return [
                month_names[number - 1]
            ]

        return []

    if period_type == "QUARTERLY":

        quarter_months = {
            1: month_names[0:3],
            2: month_names[3:6],
            3: month_names[6:9],
            4: month_names[9:12],
        }

        return quarter_months.get(
            number,
            [],
        )

    if period_type == "BIANNUAL":

        if number == 1:
            return month_names[0:6]

        if number == 2:
            return month_names[6:12]

        return []

    if period_type == "ANNUAL":

        return month_names

    return []


# ============================================================
# PERIOD LABEL
# ============================================================

def get_period_label(period):

    if not period:
        return ""

    try:

        year = getattr(
            period,
            "year",
            "",
        )

        period_type = getattr(
            period,
            "period_type",
            "",
        )

        period_number = getattr(
            period,
            "period_number",
            "",
        )

        name = getattr(
            period,
            "name",
            "",
        )

        readable_type = get_period_type_label(
            period_type
        )

        # ----------------------------------------------------
        # Prefer useful standard labels
        # ----------------------------------------------------

        number_label = get_period_number_label(
            period
        )

        if year and number_label:

            if period_type == "MONTHLY":
                return f"{year} - {number_label}"

            if period_type == "QUARTERLY":
                return f"{year} - {number_label}"

            if period_type == "BIANNUAL":
                return f"{year} - {number_label}"

            if period_type == "ANNUAL":
                return f"{year} - Annual"

        # ----------------------------------------------------
        # Database name
        # ----------------------------------------------------

        if name:

            if year:
                return f"{year} - {name}"

            return str(name)

        # ----------------------------------------------------
        # Generic fallback
        # ----------------------------------------------------

        if (
            year
            and period_type
            and period_number
        ):

            return (
                f"{year} - "
                f"{readable_type} "
                f"{period_number}"
            )

        if year and period_type:

            return (
                f"{year} - "
                f"{readable_type}"
            )

        if year:
            return str(year)

        return str(period)

    except Exception:

        return str(period)


# ============================================================
# ORGANIZATION DESCENDANTS
# ============================================================

def get_descendant_organization_ids(
    organizations,
    organization_id,
):
    """
    Return selected organization plus all descendants.
    """

    organization_ids = {
        organization_id
    }

    changed = True

    while changed:

        changed = False

        for organization in organizations:

            if (
                organization.parent_id
                in organization_ids
            ):

                if (
                    organization.id
                    not in organization_ids
                ):

                    organization_ids.add(
                        organization.id
                    )

                    changed = True

    return organization_ids


# ============================================================
# BUILD ORGANIZATION TREE
# ============================================================

def build_organization_tree(
    organizations,
    selected_ids=None,
):

    selected_ids = selected_ids or set()

    organization_map = {}

    for organization in organizations:

        organization_map[
            organization.id
        ] = {

            "id":
                organization.id,

            "name":
                organization.name,

            "code":
                organization.code,

            "unit_type":
                organization.unit_type,

            "unit_type_label":
                organization.get_unit_type_display(),

            "parent_id":
                organization.parent_id,

            "selected":
                organization.id in selected_ids,

            "children":
                [],
        }

    roots = []

    for organization in organizations:

        node = organization_map[
            organization.id
        ]

        if (
            organization.parent_id
            and organization.parent_id
            in organization_map
        ):

            organization_map[
                organization.parent_id
            ]["children"].append(
                node
            )

        else:

            roots.append(node)

    def sort_nodes(nodes):

        nodes.sort(
            key=lambda item: (
                item["unit_type"],
                item["name"].lower(),
            )
        )

        for node in nodes:
            sort_nodes(
                node["children"]
            )

    sort_nodes(roots)

    return roots


# ============================================================
# ORGANIZATION SELECTION
# ============================================================

def get_selected_organization_ids(
    request,
    accessible_organizations,
):

    raw_ids = request.GET.getlist(
        "organization"
    )

    selected_ids = set()

    accessible_ids = {
        organization.id
        for organization
        in accessible_organizations
    }

    for raw_id in raw_ids:

        try:

            organization_id = int(
                raw_id
            )

            if (
                organization_id
                in accessible_ids
            ):

                selected_ids.add(
                    organization_id
                )

        except (
            ValueError,
            TypeError,
        ):

            continue

    return selected_ids


# ============================================================
# FACILITIES FOR ORGANIZATIONS
# ============================================================

def facilities_for_organizations(
    accessible_facilities,
    accessible_organizations,
    selected_organization_ids,
):

    if not selected_organization_ids:

        return accessible_facilities

    all_organization_ids = set()

    for organization_id in selected_organization_ids:

        descendant_ids = (
            get_descendant_organization_ids(
                accessible_organizations,
                organization_id,
            )
        )

        all_organization_ids.update(
            descendant_ids
        )

    return (
        accessible_facilities
        .filter(
            organization_id__in=
            all_organization_ids
        )
        .distinct()
    )


# ============================================================
# PERIOD SORT KEY
# ============================================================

def period_sort_key(period):

    type_order = {
        "MONTHLY": 1,
        "QUARTERLY": 2,
        "BIANNUAL": 3,
        "ANNUAL": 4,
    }

    return (
        period.year or 0,
        type_order.get(
            period.period_type,
            99,
        ),
        period.period_number or 0,
        str(
            period.name or ""
        ).lower(),
        period.id,
    )


# ============================================================
# PERIOD OPTION
# ============================================================

def build_period_option(
    period,
    selected_period_id=None,
):

    months = get_period_months(
        period
    )

    return {

        "id":
            period.id,

        "name":
            period.name or "",

        "year":
            period.year,

        "period_type":
            period.period_type,

        "period_type_label":
            get_period_type_label(
                period.period_type
            ),

        "period_number":
            period.period_number,

        "number_label":
            get_period_number_label(
                period
            ),

        "label":
            get_period_label(
                period
            ),

        "months":
            months,

        "month_label":
            ", ".join(
                months
            ),

        "selected":
            (
                period.id
                == selected_period_id
            ),
    }


# ============================================================
# PERIOD NAVIGATION
# ============================================================

def build_period_navigation(
    available_periods,
    selected_period,
    selected_period_type,
):

    periods = list(
        available_periods
    )

    if not periods:

        return {

            "current_period_id":
                None,

            "current_period_label":
                "",

            "current_period_name":
                "",

            "current_period_year":
                None,

            "current_period_type":
                "",

            "current_period_type_label":
                "",

            "current_period_number":
                None,

            "current_period_months":
                [],

            "previous_period_id":
                None,

            "previous_period_label":
                "",

            "next_period_id":
                None,

            "next_period_label":
                "",

            "has_previous":
                False,

            "has_next":
                False,
        }

    navigation_periods = periods

    if selected_period_type:

        navigation_periods = [
            period
            for period in navigation_periods
            if period.period_type
            == selected_period_type
        ]

    navigation_periods = sorted(
        navigation_periods,
        key=period_sort_key,
    )

    current_period = selected_period

    if current_period is None:

        if navigation_periods:
            current_period = navigation_periods[-1]

        else:
            current_period = sorted(
                periods,
                key=period_sort_key,
            )[-1]

    previous_period = None
    next_period = None

    for index, period in enumerate(
        navigation_periods
    ):

        if period.id == current_period.id:

            if index > 0:
                previous_period = (
                    navigation_periods[
                        index - 1
                    ]
                )

            if index < len(
                navigation_periods
            ) - 1:

                next_period = (
                    navigation_periods[
                        index + 1
                    ]
                )

            break

    return {

        "current_period_id":
            current_period.id,

        "current_period_label":
            get_period_label(
                current_period
            ),

        "current_period_name":
            current_period.name or "",

        "current_period_year":
            current_period.year,

        "current_period_type":
            current_period.period_type,

        "current_period_type_label":
            get_period_type_label(
                current_period.period_type
            ),

        "current_period_number":
            current_period.period_number,

        "current_period_months":
            get_period_months(
                current_period
            ),

        "previous_period_id":
            (
                previous_period.id
                if previous_period
                else None
            ),

        "previous_period_label":
            (
                get_period_label(
                    previous_period
                )
                if previous_period
                else ""
            ),

        "next_period_id":
            (
                next_period.id
                if next_period
                else None
            ),

        "next_period_label":
            (
                get_period_label(
                    next_period
                )
                if next_period
                else ""
            ),

        "has_previous":
            previous_period is not None,

        "has_next":
            next_period is not None,
    }


# ============================================================
# LQAS PERIOD MATCHING
# ============================================================

def get_lqas_period_values(period):

    """
    LQAS currently stores period as text.

    This helper generates the common text representations
    that can correspond to an AssessmentPeriod.
    """

    values = set()

    if not period:
        return values

    name = getattr(
        period,
        "name",
        "",
    )

    period_number = getattr(
        period,
        "period_number",
        None,
    )

    period_type = getattr(
        period,
        "period_type",
        "",
    )

    year = getattr(
        period,
        "year",
        None,
    )

    if name:
        values.add(str(name))

    if period_number:
        values.add(str(period_number))

    number_label = get_period_number_label(
        period
    )

    if number_label:
        values.add(str(number_label))

    if period_type and period_number:

        values.add(
            f"{period_type} {period_number}"
        )

        values.add(
            f"{get_period_type_label(period_type)} "
            f"{period_number}"
        )

    if year and number_label:

        values.add(
            f"{year} - {number_label}"
        )

        values.add(
            f"{year} {number_label}"
        )

    if year and name:

        values.add(
            f"{year} - {name}"
        )

        values.add(
            f"{year} {name}"
        )

    return values


# ============================================================
# ANALYTICS DASHBOARD
# URL: /analytics/
# ============================================================

@login_required
def analytics_dashboard(request):

    # ========================================================
    # PROFILE
    # ========================================================

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    # ========================================================
    # ACCESSIBLE ORGANIZATIONS
    # ========================================================

    accessible_organizations = (
        profile
        .accessible_organizations()
        .select_related(
            "parent"
        )
        .order_by(
            "name"
        )
    )

    accessible_organization_list = list(
        accessible_organizations
    )

    accessible_organization_ids = {
        organization.id
        for organization
        in accessible_organization_list
    }

    # ========================================================
    # ACCESSIBLE FACILITIES
    # ========================================================

    accessible_facilities = (
        profile
        .accessible_facilities()
        .select_related(
            "organization"
        )
        .order_by(
            "name"
        )
    )

    # ========================================================
    # FILTER VALUES
    # ========================================================

    selected_year = (
        request.GET.get(
            "year",
            "",
        )
        .strip()
    )

    selected_period_type = (
        request.GET.get(
            "period_type",
            "",
        )
        .strip()
        .upper()
    )

    selected_period = (
        request.GET.get(
            "period",
            "",
        )
        .strip()
    )

    selected_facility = (
        request.GET.get(
            "facility",
            "",
        )
        .strip()
    )

    comparison_type = (
        request.GET.get(
            "comparison",
            "FACILITY",
        )
        .strip()
        .upper()
    )

    # ========================================================
    # VALID PERIOD TYPES
    # ========================================================

    valid_period_types = {
        "MONTHLY",
        "QUARTERLY",
        "BIANNUAL",
        "ANNUAL",
    }

    if selected_period_type not in valid_period_types:

        selected_period_type = ""

    # ========================================================
    # YEAR
    # ========================================================

    year_value = None

    if selected_year:

        try:

            year_value = int(
                selected_year
            )

        except (
            ValueError,
            TypeError,
        ):

            selected_year = ""
            year_value = None

    # ========================================================
    # ALL PERIODS
    # ========================================================

    all_periods = list(
        AssessmentPeriod.objects
        .all()
    )

    all_periods = sorted(
        all_periods,
        key=period_sort_key,
    )

    # ========================================================
    # AVAILABLE YEARS
    # ========================================================

    assessment_years = (
        AssessmentPeriod.objects
        .exclude(
            year__isnull=True
        )
        .values_list(
            "year",
            flat=True,
        )
        .distinct()
    )

    lqas_years = (
        LQASAssessment.objects
        .filter(
            facility__in=
            accessible_facilities
        )
        .exclude(
            year__isnull=True
        )
        .values_list(
            "year",
            flat=True,
        )
        .distinct()
    )

    available_years = sorted(
        set(
            list(
                assessment_years
            )
            +
            list(
                lqas_years
            )
        ),
        reverse=True,
    )

    # ========================================================
    # PERIOD SELECTOR YEARS
    # ========================================================

    period_selector_years = sorted(
        set(
            AssessmentPeriod.objects
            .exclude(
                year__isnull=True
            )
            .values_list(
                "year",
                flat=True,
            )
        ),
        reverse=True,
    )

    # Add LQAS years too
    period_selector_years = sorted(
        set(
            period_selector_years
            +
            list(lqas_years)
        ),
        reverse=True,
    )

    # ========================================================
    # DEFAULT YEAR
    # ========================================================

    period_selector_year = year_value

    if period_selector_year is None:

        if period_selector_years:

            period_selector_year = (
                period_selector_years[0]
            )

            # Use the default year for the actual
            # analytics query as well.
            year_value = (
                period_selector_year
            )

            selected_year = str(
                period_selector_year
            )

    # ========================================================
    # PERIOD TYPE DEFAULT
    # ========================================================

    if not selected_period_type:

        # Prefer the type that exists for the selected year.
        available_types_for_year = [
            period.period_type
            for period in all_periods
            if (
                year_value is None
                or period.year == year_value
            )
            and period.period_type
            in valid_period_types
        ]

        if "MONTHLY" in available_types_for_year:
            selected_period_type = "MONTHLY"

        elif "QUARTERLY" in available_types_for_year:
            selected_period_type = "QUARTERLY"

        elif "BIANNUAL" in available_types_for_year:
            selected_period_type = "BIANNUAL"

        elif "ANNUAL" in available_types_for_year:
            selected_period_type = "ANNUAL"

    # ========================================================
    # PERIOD OPTIONS
    #
    # These are now controlled by:
    #
    # YEAR
    # +
    # PERIOD TYPE
    #
    # Example:
    #
    # 2026 + MONTHLY
    #     -> January ... December
    #
    # 2026 + QUARTERLY
    #     -> Q1 ... Q4
    #
    # 2026 + BIANNUAL
    #     -> H1 ... H2
    #
    # 2026 + ANNUAL
    #     -> Annual
    # ========================================================

    selector_periods = all_periods

    if year_value is not None:

        selector_periods = [
            period
            for period
            in selector_periods
            if period.year == year_value
        ]

    if selected_period_type:

        selector_periods = [
            period
            for period
            in selector_periods
            if (
                period.period_type
                == selected_period_type
            )
        ]

    selector_periods = sorted(
        selector_periods,
        key=period_sort_key,
    )

    # ========================================================
    # SELECTED PERIOD ID
    # ========================================================

    selected_period_id = None

    if selected_period:

        try:

            requested_period_id = int(
                selected_period
            )

        except (
            ValueError,
            TypeError,
        ):

            requested_period_id = None

        if requested_period_id:

            matching_period = next(
                (
                    period
                    for period
                    in selector_periods
                    if period.id
                    == requested_period_id
                ),
                None,
            )

            if matching_period:

                selected_period_id = (
                    matching_period.id
                )

    # ========================================================
    # DEFAULT PERIOD
    #
    # If the user selected a year/type but not a specific
    # period, choose the latest available period of that
    # type/year.
    # ========================================================

    if (
        selected_period_id is None
        and selector_periods
    ):

        selected_period_id = (
            selector_periods[-1].id
        )

    selected_period_object = None

    if selected_period_id:

        selected_period_object = next(
            (
                period
                for period
                in selector_periods
                if period.id
                == selected_period_id
            ),
            None,
        )

    # ========================================================
    # PERIOD OPTIONS
    # ========================================================

    period_options = [

        build_period_option(
            period,
            selected_period_id,
        )

        for period
        in selector_periods
    ]

    # ========================================================
    # PERIOD GROUPS
    # ========================================================

    period_groups = {

        "MONTHLY": [],
        "QUARTERLY": [],
        "BIANNUAL": [],
        "ANNUAL": [],
    }

    # Build groups from selected year so the frontend
    # can still switch between types easily.

    year_periods = all_periods

    if year_value is not None:

        year_periods = [
            period
            for period
            in year_periods
            if period.year == year_value
        ]

    for period in sorted(
        year_periods,
        key=period_sort_key,
    ):

        if period.period_type in period_groups:

            period_groups[
                period.period_type
            ].append(
                build_period_option(
                    period,
                    selected_period_id,
                )
            )

    # ========================================================
    # PERIOD NAVIGATION
    # ========================================================

    period_navigation = (
        build_period_navigation(
            selector_periods,
            selected_period_object,
            selected_period_type,
        )
    )

    # ========================================================
    # SELECTED ORGANIZATIONS
    # ========================================================

    selected_organization_ids = (
        get_selected_organization_ids(
            request,
            accessible_organization_list,
        )
    )

    # ========================================================
    # FACILITIES BASED ON ORGANIZATION
    # ========================================================

    facilities = (
        facilities_for_organizations(
            accessible_facilities,
            accessible_organization_list,
            selected_organization_ids,
        )
    )

    # ========================================================
    # ORGANIZATION TREE
    # ========================================================

    organization_tree = (
        build_organization_tree(
            accessible_organization_list,
            selected_organization_ids,
        )
    )

    # ========================================================
    # FACILITY FILTER
    # ========================================================

    if selected_facility:

        try:

            facility_id = int(
                selected_facility
            )

        except (
            ValueError,
            TypeError,
        ):

            facility_id = None

        if (
            facility_id
            and facilities.filter(
                id=facility_id
            ).exists()
        ):

            facilities = (
                facilities
                .filter(
                    id=facility_id
                )
            )

        else:

            selected_facility = ""

    # ========================================================
    # SINGLE PERIOD QUERY
    # ========================================================

    # The Analytics page now filters by ONE selected period.
    #
    # This is much clearer for users:
    #
    # 2026 -> Monthly -> September
    #
    # 2026 -> Quarterly -> Q3
    #
    # 2026 -> Biannual -> H2
    #
    # 2026 -> Annual -> Annual
    #
    selected_period_filter_id = (
        selected_period_id
    )

    # ========================================================
    # ASSESSMENT BASE QUERYSET
    # ========================================================

    assessments = (
        Assessment.objects
        .filter(
            facility__in=facilities
        )
        .select_related(
            "facility",
            "facility__organization",
            "period",
        )
        .order_by(
            "-created_at"
        )
    )

    # ========================================================
    # APPLY YEAR
    # ========================================================

    if year_value is not None:

        assessments = (
            assessments
            .filter(
                period__year=
                year_value
            )
        )

    # ========================================================
    # APPLY PERIOD TYPE
    # ========================================================

    if selected_period_type:

        assessments = (
            assessments
            .filter(
                period__period_type=
                selected_period_type
            )
        )

    # ========================================================
    # APPLY SPECIFIC PERIOD
    # ========================================================

    if selected_period_filter_id:

        assessments = (
            assessments
            .filter(
                period_id=
                selected_period_filter_id
            )
        )

    # ========================================================
    # LQAS BASE QUERYSET
    # ========================================================

    lqas_assessments = (
        LQASAssessment.objects
        .filter(
            facility__in=facilities
        )
        .select_related(
            "facility",
            "facility__organization",
        )
        .order_by(
            "-created_at"
        )
    )

    # ========================================================
    # LQAS YEAR
    # ========================================================

    if year_value is not None:

        lqas_assessments = (
            lqas_assessments
            .filter(
                year=year_value
            )
        )

    # ========================================================
    # LQAS PERIOD
    # ========================================================

    if selected_period_object:

        lqas_period_values = (
            get_lqas_period_values(
                selected_period_object
            )
        )

        if lqas_period_values:

            lqas_assessments = (
                lqas_assessments
                .filter(
                    period__in=
                    lqas_period_values
                )
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    total_assessments = (
        assessments.count()
    )

    total_lqas = (
        lqas_assessments.count()
    )

    # ========================================================
    # AVERAGE ASSESSMENT
    # ========================================================

    average_assessment_score = (
        safe_score(
            assessments
            .exclude(
                total_score__isnull=True
            )
            .aggregate(
                average=Avg(
                    "total_score"
                )
            )
            .get(
                "average"
            )
        )
    )

    # ========================================================
    # AVERAGE LQAS
    # ========================================================

    average_lqas_score = (
        safe_score(
            lqas_assessments
            .exclude(
                percentage__isnull=True
            )
            .aggregate(
                average=Avg(
                    "percentage"
                )
            )
            .get(
                "average"
            )
        )
    )

    # ========================================================
    # FACILITY PERFORMANCE
    # ========================================================

    facility_performance = []

    for facility in facilities.order_by(
        "name"
    ):

        facility_assessments = (
            assessments
            .filter(
                facility_id=
                facility.id
            )
        )

        facility_lqas = (
            lqas_assessments
            .filter(
                facility_id=
                facility.id
            )
        )

        assessment_score = (
            facility_assessments
            .exclude(
                total_score__isnull=True
            )
            .aggregate(
                average=Avg(
                    "total_score"
                )
            )
            .get(
                "average"
            )
        )

        lqas_score = (
            facility_lqas
            .exclude(
                percentage__isnull=True
            )
            .aggregate(
                average=Avg(
                    "percentage"
                )
            )
            .get(
                "average"
            )
        )

        assessment_score = safe_score(
            assessment_score
        )

        lqas_score = safe_score(
            lqas_score
        )

        has_assessment = (
            facility_assessments
            .exclude(
                total_score__isnull=True
            )
            .exists()
        )

        has_lqas = (
            facility_lqas
            .exclude(
                percentage__isnull=True
            )
            .exists()
        )

        # ----------------------------------------------------
        # COMBINED SCORE
        #
        # Assessment = 70%
        # LQAS = 30%
        # ----------------------------------------------------

        if has_assessment and has_lqas:

            combined_score = (
                assessment_score
                *
                Decimal("0.70")
            ) + (
                lqas_score
                *
                Decimal("0.30")
            )

        elif has_assessment:

            combined_score = (
                assessment_score
            )

        elif has_lqas:

            combined_score = (
                lqas_score
            )

        else:

            combined_score = Decimal(
                "0.00"
            )

        facility_performance.append(
            {

                "id":
                    facility.id,

                "name":
                    facility.name,

                "organization":
                    (
                        facility.organization.name
                        if facility.organization
                        else ""
                    ),

                "assessment_score":
                    float(
                        assessment_score
                    ),

                "lqas_score":
                    float(
                        lqas_score
                    ),

                "combined_score":
                    float(
                        safe_score(
                            combined_score
                        )
                    ),

                "assessment_count":
                    facility_assessments.count(),

                "lqas_count":
                    facility_lqas.count(),
            }
        )

    # ========================================================
    # FACILITY RANKING
    # ========================================================

    facility_ranking = sorted(
        facility_performance,
        key=lambda item: (
            item["combined_score"],
            item["assessment_score"],
            item["lqas_score"],
        ),
        reverse=True,
    )

    for index, item in enumerate(
        facility_ranking,
        start=1,
    ):

        item["rank"] = index

        score = item[
            "combined_score"
        ]

        if score >= 90:

            item[
                "performance_level"
            ] = "Excellent"

        elif score >= 75:

            item[
                "performance_level"
            ] = "Good"

        elif score >= 50:

            item[
                "performance_level"
            ] = "Needs Improvement"

        else:

            item[
                "performance_level"
            ] = "Critical"

    # ========================================================
    # TOP / BOTTOM
    # ========================================================

    top_facilities = (
        facility_ranking[:10]
    )

    bottom_facilities = list(
        reversed(
            facility_ranking[-10:]
        )
    )

    # ========================================================
    # ORGANIZATION PERFORMANCE
    # ========================================================

    organization_scores = (
        defaultdict(list)
    )

    for item in facility_performance:

        organization_name = item[
            "organization"
        ]

        if organization_name:

            organization_scores[
                organization_name
            ].append(
                item[
                    "combined_score"
                ]
            )

    organization_performance = []

    for (
        organization_name,
        scores,
    ) in organization_scores.items():

        average_score = (

            sum(scores)
            /
            len(scores)

            if scores
            else 0
        )

        organization_performance.append(
            {

                "name":
                    organization_name,

                "score":
                    round(
                        average_score,
                        2,
                    ),

                "facility_count":
                    len(scores),
            }
        )

    organization_performance = sorted(
        organization_performance,
        key=lambda item:
            item["score"],
        reverse=True,
    )

    # ========================================================
    # DHIS2 HIERARCHY
    # ========================================================

    facility_perf_by_id = {
        item["id"]: item
        for item
        in facility_performance
    }

    facilities_by_org_id = (
        defaultdict(list)
    )

    for fac in accessible_facilities:

        if fac.organization_id:

            facilities_by_org_id[
                fac.organization_id
            ].append(
                fac
            )

    def compute_node_metrics(
        org,
        all_orgs_list,
    ):

        desc_ids = (
            get_descendant_organization_ids(
                all_orgs_list,
                org.id,
            )
        )

        matching_fac_ids = [
            f.id
            for f
            in accessible_facilities
            if f.organization_id
            in desc_ids
        ]

        matching_perfs = [
            facility_perf_by_id[fid]
            for fid
            in matching_fac_ids
            if fid in facility_perf_by_id
        ]

        total_facs = len(
            matching_fac_ids
        )

        total_assessments_cnt = sum(
            p["assessment_count"]
            for p
            in matching_perfs
        )

        total_lqas_cnt = sum(
            p["lqas_count"]
            for p
            in matching_perfs
        )

        total_reports_cnt = (
            total_assessments_cnt
            +
            total_lqas_cnt
        )

        assessment_scores = [
            p["assessment_score"]
            for p
            in matching_perfs
            if p["assessment_count"] > 0
        ]

        lqas_scores = [
            p["lqas_score"]
            for p
            in matching_perfs
            if p["lqas_count"] > 0
        ]

        combined_scores = [
            p["combined_score"]
            for p
            in matching_perfs
            if (
                p["assessment_count"] > 0
                or
                p["lqas_count"] > 0
            )
        ]

        avg_ass = (
            round(
                sum(assessment_scores)
                /
                len(assessment_scores),
                2,
            )
            if assessment_scores
            else 0.0
        )

        avg_lqas = (
            round(
                sum(lqas_scores)
                /
                len(lqas_scores),
                2,
            )
            if lqas_scores
            else 0.0
        )

        avg_comb = (
            round(
                sum(combined_scores)
                /
                len(combined_scores),
                2,
            )
            if combined_scores
            else 0.0
        )

        if avg_comb >= 90:

            perf_level = "Excellent"

        elif avg_comb >= 75:

            perf_level = "Good"

        elif avg_comb >= 50:

            perf_level = "Needs Improvement"

        elif (
            total_facs > 0
            and total_reports_cnt > 0
        ):

            perf_level = "Critical"

        else:

            perf_level = "No Data"

        return {

            "id":
                org.id,

            "name":
                org.name,

            "code":
                org.code or "",

            "unit_type":
                org.unit_type,

            "unit_type_label":
                org.get_unit_type_display(),

            "facility_count":
                total_facs,

            "assessment_count":
                total_assessments_cnt,

            "lqas_count":
                total_lqas_cnt,

            "total_reports":
                total_reports_cnt,

            "assessment_score":
                avg_ass,

            "lqas_score":
                avg_lqas,

            "combined_score":
                avg_comb,

            "performance_level":
                perf_level,
        }

    org_map = {
        org.id: org
        for org
        in accessible_organization_list
    }

    child_orgs_map = (
        defaultdict(list)
    )

    top_level_orgs = []

    for org in accessible_organization_list:

        if (
            org.parent_id
            and org.parent_id
            in org_map
        ):

            child_orgs_map[
                org.parent_id
            ].append(
                org
            )

        else:

            top_level_orgs.append(
                org
            )

    def build_hierarchy_tree_node(org):

        node_data = compute_node_metrics(
            org,
            accessible_organization_list,
        )

        children_nodes = []

        for child_org in sorted(
            child_orgs_map.get(
                org.id,
                []
            ),
            key=lambda o:
                o.name,
        ):

            children_nodes.append(
                build_hierarchy_tree_node(
                    child_org
                )
            )

        node_data[
            "children"
        ] = children_nodes

        direct_facilities = []

        for fac in sorted(
            facilities_by_org_id.get(
                org.id,
                []
            ),
            key=lambda f:
                f.name,
        ):

            fac_perf = (
                facility_perf_by_id.get(
                    fac.id,
                    {
                        "id":
                            fac.id,

                        "name":
                            fac.name,

                        "organization":
                            (
                                fac.organization.name
                                if fac.organization
                                else ""
                            ),

                        "assessment_score":
                            0.0,

                        "lqas_score":
                            0.0,

                        "combined_score":
                            0.0,

                        "assessment_count":
                            0,

                        "lqas_count":
                            0,

                        "total_reports":
                            0,

                        "performance_level":
                            "No Data",
                    },
                )
            )

            if (
                "total_reports"
                not in fac_perf
            ):

                fac_perf[
                    "total_reports"
                ] = (
                    fac_perf.get(
                        "assessment_count",
                        0,
                    )
                    +
                    fac_perf.get(
                        "lqas_count",
                        0,
                    )
                )

            direct_facilities.append(
                fac_perf
            )

        node_data[
            "direct_facilities"
        ] = direct_facilities

        return node_data

    dhis2_hierarchy_tree = [

        build_hierarchy_tree_node(
            org
        )

        for org

        in sorted(
            top_level_orgs,
            key=lambda o:
                o.name,
        )
    ]

    # ========================================================
    # TREND
    #
    # Trend uses the selected YEAR + PERIOD TYPE.
    #
    # The current period is highlighted separately by the
    # frontend.
    # ========================================================

    trend_map = (
        defaultdict(list)
    )

    trend_assessments = (
        Assessment.objects
        .filter(
            facility__in=facilities
        )
        .exclude(
            total_score__isnull=True
        )
        .select_related(
            "period"
        )
        .order_by(
            "period__year",
            "period__period_type",
            "period__period_number",
            "created_at",
        )
    )

    if year_value is not None:

        trend_assessments = (
            trend_assessments
            .filter(
                period__year=
                year_value
            )
        )

    if selected_period_type:

        trend_assessments = (
            trend_assessments
            .filter(
                period__period_type=
                selected_period_type
            )
        )

    for assessment in trend_assessments:

        label = get_period_label(
            assessment.period
        )

        if not label:

            if assessment.created_at:

                label = (
                    assessment.created_at
                    .strftime(
                        "%b %Y"
                    )
                )

            else:

                label = "Unknown"

        trend_map[
            label
        ].append(
            float(
                assessment.total_score
            )
        )

    trend_labels = []
    trend_scores = []

    trend_items = list(
        trend_map.items()
    )[-12:]

    for (
        label,
        scores,
    ) in trend_items:

        trend_labels.append(
            label
        )

        trend_scores.append(
            round(
                sum(scores)
                /
                len(scores),
                2,
            )
        )

    # ========================================================
    # PERIOD COMPARISON
    # ========================================================

    period_comparison_groups = (
        defaultdict(
            lambda: {
                "scores": [],
                "year": None,
                "period_type": None,
                "period_number": None,
                "name": "",
            }
        )
    )

    comparison_assessments = (
        Assessment.objects
        .filter(
            facility__in=facilities
        )
        .exclude(
            total_score__isnull=True
        )
        .select_related(
            "period"
        )
        .order_by(
            "period__year",
            "period__period_type",
            "period__period_number",
        )
    )

    for assessment in comparison_assessments:

        period = assessment.period

        if not period:
            continue

        year = getattr(
            period,
            "year",
            "",
        )

        period_type = getattr(
            period,
            "period_type",
            "",
        )

        period_number = getattr(
            period,
            "period_number",
            "",
        )

        period_name = getattr(
            period,
            "name",
            "",
        )

        group_key = (
            year,
            period_type,
            period_number,
            period_name,
        )

        period_comparison_groups[
            group_key
        ]["scores"].append(
            float(
                assessment.total_score
            )
        )

        period_comparison_groups[
            group_key
        ]["year"] = year

        period_comparison_groups[
            group_key
        ]["period_type"] = (
            period_type
        )

        period_comparison_groups[
            group_key
        ]["period_number"] = (
            period_number
        )

        period_comparison_groups[
            group_key
        ]["name"] = period_name

    period_comparison = {

        "labels": [],
        "scores": [],
        "counts": [],
        "types": [],
        "years": [],
        "numbers": [],
    }

    comparison_groups = list(
        period_comparison_groups.values()
    )

    comparison_groups.sort(
        key=lambda group: (
            group["year"] or 0,
            {
                "MONTHLY": 1,
                "QUARTERLY": 2,
                "BIANNUAL": 3,
                "ANNUAL": 4,
            }.get(
                group["period_type"],
                99,
            ),
            group["period_number"] or 0,
        )
    )

    for group in comparison_groups:

        scores = group[
            "scores"
        ]

        if not scores:
            continue

        year = group[
            "year"
        ]

        period_type = group[
            "period_type"
        ]

        period_number = group[
            "period_number"
        ]

        period_name = group[
            "name"
        ]

        if period_name:

            if year:

                label = (
                    f"{year} - "
                    f"{period_name}"
                )

            else:

                label = str(
                    period_name
                )

        else:

            readable_type = (
                get_period_type_label(
                    period_type
                )
            )

            if (
                year
                and period_number
            ):

                if period_type == "MONTHLY":

                    number_label = (
                        get_period_number_label(
                            type(
                                "PeriodObject",
                                (),
                                {
                                    "period_type":
                                        period_type,
                                    "period_number":
                                        period_number,
                                },
                            )()
                        )
                    )

                    label = (
                        f"{year} - "
                        f"{number_label}"
                    )

                elif period_type == "QUARTERLY":

                    label = (
                        f"{year} - "
                        f"Q{period_number}"
                    )

                elif period_type == "BIANNUAL":

                    label = (
                        f"{year} - "
                        f"H{period_number}"
                    )

                else:

                    label = (
                        f"{year} - "
                        f"{readable_type} "
                        f"{period_number}"
                    )

            elif year:

                label = (
                    f"{year} - "
                    f"{readable_type}"
                )

            else:

                label = readable_type

        period_comparison[
            "labels"
        ].append(
            label
        )

        period_comparison[
            "scores"
        ].append(
            round(
                sum(scores)
                /
                len(scores),
                2,
            )
        )

        period_comparison[
            "counts"
        ].append(
            len(scores)
        )

        period_comparison[
            "types"
        ].append(
            period_type
        )

        period_comparison[
            "years"
        ].append(
            year
        )

        period_comparison[
            "numbers"
        ].append(
            period_number
        )

    # ========================================================
    # PERIOD TYPE COMPARISON
    # ========================================================

    period_type_groups = (
        defaultdict(list)
    )

    for assessment in (
        Assessment.objects
        .filter(
            facility__in=facilities
        )
        .exclude(
            total_score__isnull=True
        )
        .select_related(
            "period"
        )
    ):

        period = assessment.period

        if not period:
            continue

        if (
            year_value is not None
            and period.year != year_value
        ):
            continue

        period_type = getattr(
            period,
            "period_type",
            "",
        )

        if not period_type:
            continue

        period_type_groups[
            period_type
        ].append(
            float(
                assessment.total_score
            )
        )

    period_type_order = [
        "MONTHLY",
        "QUARTERLY",
        "BIANNUAL",
        "ANNUAL",
    ]

    period_type_comparison = []

    for period_type in period_type_order:

        scores = (
            period_type_groups.get(
                period_type,
                [],
            )
        )

        average_score = (

            round(
                sum(scores)
                /
                len(scores),
                2,
            )

            if scores
            else 0
        )

        period_type_comparison.append(
            {

                "type":
                    period_type,

                "label":
                    get_period_type_label(
                        period_type
                    ),

                "score":
                    average_score,

                "count":
                    len(scores),
            }
        )

    # ========================================================
    # SELECTED ORGANIZATION NAMES
    # ========================================================

    selected_organizations = [

        organization

        for organization

        in accessible_organization_list

        if organization.id
        in selected_organization_ids
    ]

    selected_organization_names = [

        organization.name

        for organization

        in selected_organizations
    ]

    selected_organization_name = (
        ", ".join(
            selected_organization_names
        )
    )

    if (
        not selected_organization_name
        and profile.organization
    ):

        selected_organization_name = (
            profile.organization.name
        )

    if (
        not selected_organization_name
        and profile.facility
    ):

        selected_organization_name = (
            profile.facility.name
        )

    # ========================================================
    # SELECTED PERIOD LABEL
    # ========================================================

    selected_period_label = ""

    if selected_period_object:

        selected_period_label = (
            get_period_label(
                selected_period_object
            )
        )

    # ========================================================
    # CHART DATA
    # ========================================================

    chart_data = {

        "trend_labels":
            trend_labels,

        "trend_scores":
            trend_scores,

        "facility_labels": [

            item["name"]

            for item

            in facility_ranking
        ],

        "facility_scores": [

            item["combined_score"]

            for item

            in facility_ranking
        ],

        "facility_assessment_scores": [

            item["assessment_score"]

            for item

            in facility_ranking
        ],

        "facility_lqas_scores": [

            item["lqas_score"]

            for item

            in facility_ranking
        ],

        "organization_labels": [

            item["name"]

            for item

            in organization_performance
        ],

        "organization_scores": [

            item["score"]

            for item

            in organization_performance
        ],

        "period_labels":
            period_comparison[
                "labels"
            ],

        "period_scores":
            period_comparison[
                "scores"
            ],

        "period_counts":
            period_comparison[
                "counts"
            ],

        "period_types":
            period_comparison[
                "types"
            ],

        "period_years":
            period_comparison[
                "years"
            ],

        "period_numbers":
            period_comparison[
                "numbers"
            ],

        "period_type_labels": [

            item["label"]

            for item

            in period_type_comparison
        ],

        "period_type_scores": [

            item["score"]

            for item

            in period_type_comparison
        ],

        "period_type_counts": [

            item["count"]

            for item

            in period_type_comparison
        ],
    }

    # ========================================================
    # RECENT ASSESSMENTS
    # ========================================================

    recent_assessments = (
        assessments
        .select_related(
            "facility",
            "period",
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # ========================================================
    # RECENT LQAS
    # ========================================================

    recent_lqas = (
        lqas_assessments
        .select_related(
            "facility"
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    # ========================================================
    # STATUS COUNTS
    # ========================================================

    submitted_status = assessment_status(
        "SUBMITTED"
    )

    reviewed_status = assessment_status(
        "REVIEWED"
    )

    approved_status = assessment_status(
        "APPROVED"
    )

    draft_status = assessment_status(
        "DRAFT"
    )

    returned_status = assessment_status(
        "RETURNED"
    )

    status_counts = {

        "submitted":
            assessments.filter(
                status=submitted_status
            ).count(),

        "reviewed":
            assessments.filter(
                status=reviewed_status
            ).count(),

        "approved":
            assessments.filter(
                status=approved_status
            ).count(),

        "draft":
            assessments.filter(
                status=draft_status
            ).count(),

        "returned":
            assessments.filter(
                status=returned_status
            ).count(),
    }

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        # ----------------------------------------------------
        # PROFILE
        # ----------------------------------------------------

        "profile":
            profile,

        # ----------------------------------------------------
        # ORGANIZATION
        # ----------------------------------------------------

        "organization_name":
            selected_organization_name,

        "organizations":
            accessible_organization_list,

        "accessible_organizations":
            accessible_organization_list,

        "organization_tree":
            organization_tree,

        "dhis2_hierarchy_tree":
            dhis2_hierarchy_tree,

        "selected_organization_ids":
            selected_organization_ids,

        "selected_organization_names":
            selected_organization_names,

        "facilities":
            facilities,

        "accessible_facilities":
            accessible_facilities,

        # ----------------------------------------------------
        # YEAR FILTER
        # ----------------------------------------------------

        "available_years":
            available_years,

        "years":
            available_years,

        "selected_year":
            selected_year,

        "period_selector_year":
            period_selector_year,

        "period_selector_years":
            period_selector_years,

        # ----------------------------------------------------
        # PERIOD FILTER
        # ----------------------------------------------------

        "selected_period_type":
            selected_period_type,

        "selected_period":
            (
                str(
                    selected_period_id
                )
                if selected_period_id
                else ""
            ),

        "selected_period_id":
            selected_period_id,

        "selected_period_object":
            selected_period_object,

        "selected_period_label":
            selected_period_label,

        "period_options":
            period_options,

        "period_groups":
            period_groups,

        "period_navigation":
            period_navigation,

        # ----------------------------------------------------
        # ALL PERIODS
        # ----------------------------------------------------

        "all_periods":
            all_periods,

        # ----------------------------------------------------
        # FACILITY
        # ----------------------------------------------------

        "selected_facility":
            selected_facility,

        # ----------------------------------------------------
        # COMPATIBILITY
        # ----------------------------------------------------

        "selected_organization":

            (
                str(
                    next(
                        iter(
                            selected_organization_ids
                        )
                    )
                )

                if selected_organization_ids

                else ""
            ),

        "selected_organization_name":
            selected_organization_name,

        "comparison_type":
            comparison_type,

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        "total_assessments":
            total_assessments,

        "total_lqas":
            total_lqas,

        "total_reports":
            (
                total_assessments
                +
                total_lqas
            ),

        "average_assessment_score":
            average_assessment_score,

        "average_lqas_score":
            average_lqas_score,

        "average_assessment":
            average_assessment_score,

        "average_lqas":
            average_lqas_score,

        "facility_count":
            facilities.count(),

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        "status_counts":
            status_counts,

        "submitted_count":
            status_counts["submitted"],

        "reviewed_count":
            status_counts["reviewed"],

        "approved_count":
            status_counts["approved"],

        "draft_count":
            status_counts["draft"],

        "returned_count":
            status_counts["returned"],

        # ----------------------------------------------------
        # FACILITY PERFORMANCE
        # ----------------------------------------------------

        "facility_performance":
            facility_performance,

        "facility_ranking":
            facility_ranking,

        "top_facilities":
            top_facilities,

        "bottom_facilities":
            bottom_facilities,

        # ----------------------------------------------------
        # ORGANIZATION PERFORMANCE
        # ----------------------------------------------------

        "organization_performance":
            organization_performance,

        # ----------------------------------------------------
        # PERIOD ANALYTICS
        # ----------------------------------------------------

        "period_comparison":
            period_comparison,

        "period_type_comparison":
            period_type_comparison,

        # ----------------------------------------------------
        # CHART DATA
        # ----------------------------------------------------

        "chart_data":
            json.dumps(
                chart_data
            ),

        # ----------------------------------------------------
        # RECENT DATA
        # ----------------------------------------------------

        "recent_assessments":
            recent_assessments,

        "recent_lqas":
            recent_lqas,
    }

    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "core/analytics_dashboard.html",
        context,
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@login_required
def notifications_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    accessible_facilities = (
        profile
        .accessible_facilities()
        .filter(
            active=True
        )
    )

    health_centers = (
        accessible_facilities
        .filter(
            facility_type=
            Facility.FacilityType.HEALTH_CENTER
        )
    )

    expected_count = (
        health_centers.count()
    )

    active_period = (
        AssessmentPeriod.objects
        .filter(
            active=True
        )
        .order_by(
            "-year",
            "-end_month",
        )
        .first()
    )

    if not active_period:

        active_period = (
            AssessmentPeriod.objects
            .order_by(
                "-year",
                "-end_month",
            )
            .first()
        )

    reported_count = 0

    if (
        expected_count > 0
        and active_period
    ):

        reported_count = (
            Assessment.objects
            .filter(
                facility__in=
                health_centers,
                period=
                active_period,
                status__in=[
                    Assessment.Status.SUBMITTED,
                    Assessment.Status.REVIEWED,
                    Assessment.Status.APPROVED,
                ],
            )
            .values(
                "facility"
            )
            .distinct()
            .count()
        )

    pending_count = max(
        0,
        expected_count
        -
        reported_count,
    )

    reporting_percentage = (
        round(
            (
                reported_count
                /
                expected_count
                *
                100
            ),
            1,
        )
        if expected_count > 0
        else 0.0
    )

    context = {

        "profile":
            profile,

        "active_period":
            active_period,

        "expected_count":
            expected_count,

        "reported_count":
            reported_count,

        "pending_count":
            pending_count,

        "reporting_percentage":
            reporting_percentage,
    }

    return render(
        request,
        "core/notifications_dashboard.html",
        context,
    )


# ============================================================
# FEEDBACK
# ============================================================

@login_required
def feedback_dashboard(request):

    profile = get_profile(
        request
    )

    if not profile:

        return redirect(
            "accounts:login"
        )

    return redirect(
        "feedback:dashboard"
    )

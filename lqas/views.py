from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Facility, OrganizationUnit

from .models import LQASAssessment, LQASResponse


# ============================================================
# PROFILE / ACCESS HELPERS
# ============================================================

def get_active_profile(request):
    """
    Return the active EHIR profile of the logged-in user.
    """
    try:
        profile = request.user.profile

        if hasattr(profile, "active") and not profile.active:
            return None

        return profile

    except Exception:
        return None


def get_role(profile):
    """
    Safely return the user's role.
    """
    if not profile:
        return None

    return getattr(profile, "role", None)


# ============================================================
# FACILITY ACCESS
# ============================================================

def get_accessible_facilities(profile):
    """
    Return all facilities the logged-in user is allowed to see.
    """

    if not profile:
        return Facility.objects.none()

    # Use the project's existing access method when available.
    try:
        facilities = profile.accessible_facilities()

        if facilities is not None:
            return facilities
    except Exception:
        pass

    role = get_role(profile)

    # --------------------------------------------------------
    # Facility user
    # --------------------------------------------------------

    if role == "FACILITY_USER":

        facility = getattr(profile, "facility", None)

        if facility:
            return Facility.objects.filter(
                pk=facility.pk
            )

        return Facility.objects.none()

    # --------------------------------------------------------
    # Ministry
    # --------------------------------------------------------

    if role == "MINISTRY_ADMIN":
        return Facility.objects.all()

    # --------------------------------------------------------
    # Region / Sub-city / other organizational users
    # --------------------------------------------------------

    organization = getattr(
        profile,
        "organization",
        None,
    )

    if not organization:
        return Facility.objects.none()

    organization_ids = get_organization_tree_ids(
        organization
    )

    return Facility.objects.filter(
        organization_id__in=organization_ids
    )


# ============================================================
# ORGANIZATION HIERARCHY
# ============================================================

def get_organization_tree_ids(unit):
    """
    Return the selected organization and all descendants.
    """

    if not unit:
        return []

    ids = [unit.pk]

    children = OrganizationUnit.objects.filter(
        parent=unit
    ).only("id")

    for child in children:
        ids.extend(
            get_organization_tree_ids(child)
        )

    return ids


def can_access_organization(profile, unit):
    """
    Check whether a user can access an organization unit.
    """

    if not profile or not unit:
        return False

    role = get_role(profile)

    # Ministry sees everything.
    if role == "MINISTRY_ADMIN":
        return True

    organization = getattr(
        profile,
        "organization",
        None,
    )

    if not organization:
        return False

    accessible_ids = get_organization_tree_ids(
        organization
    )

    return unit.pk in accessible_ids


def can_access_facility(profile, facility):
    """
    Check whether a user can access a facility.
    """

    if not profile or not facility:
        return False

    role = get_role(profile)

    # Ministry sees all facilities.
    if role == "MINISTRY_ADMIN":
        return True

    # Facility user sees only own facility.
    if role == "FACILITY_USER":

        own_facility = getattr(
            profile,
            "facility",
            None,
        )

        return (
            own_facility is not None
            and own_facility.pk == facility.pk
        )

    accessible = get_accessible_facilities(
        profile
    )

    return accessible.filter(
        pk=facility.pk
    ).exists()


# ============================================================
# ORGANIZATION CHILDREN
# ============================================================

def get_visible_children(profile, unit):
    """
    Return child organizations that contain at least one
    accessible facility.
    """

    children = OrganizationUnit.objects.filter(
        parent=unit
    ).order_by("name")

    result = []

    accessible_facilities = (
        get_accessible_facilities(profile)
    )

    for child in children:

        descendant_ids = (
            get_organization_tree_ids(child)
        )

        has_facilities = (
            accessible_facilities.filter(
                organization_id__in=descendant_ids
            ).exists()
        )

        if has_facilities:
            result.append(child)

    return result


# ============================================================
# FILTER & PERIOD HELPERS
# ============================================================

LQAS_MONTH_CHOICES = [
    ("MONTHLY-1", "Monthly - 1 (January / Meskerem)"),
    ("MONTHLY-2", "Monthly - 2 (February / Tikimt)"),
    ("MONTHLY-3", "Monthly - 3 (March / Hidar)"),
    ("MONTHLY-4", "Monthly - 4 (April / Tahsas)"),
    ("MONTHLY-5", "Monthly - 5 (May / Tir)"),
    ("MONTHLY-6", "Monthly - 6 (June / Yakatit)"),
    ("MONTHLY-7", "Monthly - 7 (July / Magabit)"),
    ("MONTHLY-8", "Monthly - 8 (August / Miyazya)"),
    ("MONTHLY-9", "Monthly - 9 (September / Ginbot)"),
    ("MONTHLY-10", "Monthly - 10 (October / Sene)"),
    ("MONTHLY-11", "Monthly - 11 (November / Hamle)"),
    ("MONTHLY-12", "Monthly - 12 (December / Nehase)"),
]

def get_lqas_filter_options(accessible_facilities=None):
    """
    Return available years and month/period choices for LQAS filtering.
    """
    queryset = LQASAssessment.objects.all()
    if accessible_facilities is not None:
        queryset = queryset.filter(facility__in=accessible_facilities)

    db_years = (
        queryset.values_list("year", flat=True)
        .distinct()
        .order_by("-year")
    )
    years = list(db_years)
    
    # Ensure current/common Ethiopian years are present in dropdown
    for default_year in [2018, 2017, 2016, 2015]:
        if default_year not in years:
            years.append(default_year)
    years.sort(reverse=True)

    return {
        "available_years": years,
        "available_periods": LQAS_MONTH_CHOICES,
    }


def parse_lqas_filter_params(request):
    """
    Extract and validate year and period filter parameters from GET.
    """
    selected_year = request.GET.get("year", "").strip()
    selected_period = request.GET.get("period", "").strip()

    parsed_year = None
    if selected_year:
        try:
            parsed_year = int(selected_year)
        except (ValueError, TypeError):
            parsed_year = None

    return {
        "selected_year": parsed_year,
        "selected_year_str": str(parsed_year) if parsed_year else "",
        "selected_period": selected_period,
    }


# ============================================================
# ORGANIZATION TREE BUILDER FOR LQAS
# ============================================================

def build_lqas_organization_tree(
    profile,
    facility_queryset,
    selected_year=None,
    selected_period=None,
    root_unit=None,
):
    """
    Build hierarchical organization tree for LQAS:
    Ministry -> Regions -> Subcities / Zones -> Health Centers & Special Hospitals
    """
    role = get_role(profile)
    if role == "FACILITY_USER":
        return []

    facilities = list(
        facility_queryset
        .select_related(
            "organization",
            "organization__parent",
        )
        .order_by(
            "organization__name",
            "name",
        )
    )

    if not facilities:
        return []

    accessible_facility_ids = {f.pk for f in facilities}
    accessible_org_ids = {f.organization_id for f in facilities if f.organization_id}

    if not accessible_org_ids:
        return []

    organizations = list(
        OrganizationUnit.objects.filter(
            active=True,
            pk__in=accessible_org_ids,
        ).select_related("parent")
    )
    org_map = {o.pk: o for o in organizations}

    # Fetch ancestor organizations so hierarchy connects upwards
    ancestor_ids = set()
    for o in organizations:
        curr = o
        while curr and curr.parent_id:
            ancestor_ids.add(curr.parent_id)
            curr = curr.parent

    if ancestor_ids:
        ancestors = OrganizationUnit.objects.filter(
            active=True,
            pk__in=ancestor_ids,
        ).select_related("parent")
        for anc in ancestors:
            org_map[anc.pk] = anc

    # Group facilities by organization
    facilities_by_org = {}
    for f in facilities:
        if f.organization_id:
            facilities_by_org.setdefault(f.organization_id, []).append(f)

    # Fetch LQAS assessments for these facilities matching filters
    assessments_qs = LQASAssessment.objects.filter(
        facility__in=facilities,
    )
    if selected_year:
        assessments_qs = assessments_qs.filter(year=selected_year)
    if selected_period:
        assessments_qs = assessments_qs.filter(period=selected_period)

    assessments_qs = assessments_qs.order_by("-year", "-created_at")

    # Map assessments by facility
    latest_assessments_by_facility = {}
    report_count_by_facility = {}

    for ass in assessments_qs:
        f_id = ass.facility_id
        if ass.status == LQASAssessment.Status.SUBMITTED:
            report_count_by_facility[f_id] = report_count_by_facility.get(f_id, 0) + 1
        if f_id not in latest_assessments_by_facility:
            latest_assessments_by_facility[f_id] = ass

    # Determine root IDs
    if root_unit:
        root_ids = {root_unit.pk}
    elif role in ["REGION_ADMIN", "SUBCITY_ADMIN"]:
        root_ids = {profile.organization_id} if getattr(profile, "organization_id", None) else set()
    elif role == "MINISTRY_ADMIN":
        region_roots = {o.pk for o in org_map.values() if o.unit_type == OrganizationUnit.UnitType.REGION}
        if region_roots:
            root_ids = region_roots
        else:
            root_ids = {
                o.pk for o in org_map.values()
                if o.parent_id not in org_map or (o.parent and o.parent.unit_type == OrganizationUnit.UnitType.MINISTRY)
            }
    else:
        root_ids = set()

    def build_node(org):
        child_orgs = [
            item for item in org_map.values()
            if item.parent_id == org.pk
        ]
        child_orgs.sort(key=lambda item: item.name.lower())

        child_nodes = [build_node(child) for child in child_orgs]

        facility_nodes = []
        for fac in facilities_by_org.get(org.pk, []):
            if fac.pk not in accessible_facility_ids:
                continue
            latest_ass = latest_assessments_by_facility.get(fac.pk)
            rep_count = report_count_by_facility.get(fac.pk, 0)

            if latest_ass:
                status = latest_ass.status
                status_label = latest_ass.get_status_display()
                percentage = latest_ass.percentage
            else:
                status = "NOT_STARTED"
                status_label = "Not Started"
                percentage = None

            facility_nodes.append({
                "facility": fac,
                "assessment": latest_ass,
                "status": status,
                "status_label": status_label,
                "percentage": percentage,
                "report_count": rep_count,
            })

        total_facs = len(facility_nodes) + sum(c["total_facilities"] for c in child_nodes)
        all_percentages = []
        for fn in facility_nodes:
            if fn["status"] == LQASAssessment.Status.SUBMITTED and fn["percentage"] is not None:
                all_percentages.append(float(fn["percentage"]))
        for c in child_nodes:
            all_percentages.extend(c["collected_percentages"])

        avg_pct = round(sum(all_percentages) / len(all_percentages), 1) if all_percentages else None

        return {
            "organization": org,
            "children": child_nodes,
            "facilities": facility_nodes,
            "total_facilities": total_facs,
            "collected_percentages": all_percentages,
            "avg_percentage": avg_pct,
            "open": True,
        }

    tree = []
    for r_id in sorted(root_ids):
        root_org = org_map.get(r_id)
        if root_org:
            tree.append(build_node(root_org))

    return tree


# ============================================================
# LQAS HOME
# ============================================================

@login_required
def lqas_dashboard(request):
    """
    Main LQAS page.

    Ministry:
        Shows regions summary, full organization hierarchy tree with health facilities,
        and summary metrics filtered by year/month.

    Region / Sub-city:
        Opens its organization view with tree and filter.

    Facility:
        Opens own facility reports with filter.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your user profile is not configured."
        )

        return redirect("accounts:login")

    role = get_role(profile)

    # Filter parameters
    filter_params = parse_lqas_filter_params(request)
    selected_year = filter_params["selected_year"]
    selected_period = filter_params["selected_period"]

    accessible = get_accessible_facilities(profile)
    filter_options = get_lqas_filter_options(accessible)

    # --------------------------------------------------------
    # FACILITY
    # --------------------------------------------------------

    if role == "FACILITY_USER":

        facility = getattr(
            profile,
            "facility",
            None,
        )

        if not facility:

            messages.error(
                request,
                "No facility is assigned to your account."
            )

            return render(
                request,
                "lqas/dashboard.html",
                {
                    "profile": profile,
                    "role": role,
                    "facility": None,
                    "regions": [],
                    **filter_options,
                    **filter_params,
                },
            )

        query_params = request.GET.urlencode()
        url = f"/lqas/facility/{facility.pk}/"
        if query_params:
            url = f"{url}?{query_params}"
        return redirect(url)

    # --------------------------------------------------------
    # MINISTRY
    # --------------------------------------------------------

    if role == "MINISTRY_ADMIN":

        regions = OrganizationUnit.objects.filter(
            unit_type="REGION"
        ).order_by("name")

        visible_regions = []

        for region in regions:

            region_ids = (
                get_organization_tree_ids(region)
            )

            reg_facilities = accessible.filter(
                organization_id__in=region_ids
            )

            if reg_facilities.exists():

                reg_assessments = LQASAssessment.objects.filter(
                    facility__in=reg_facilities,
                    status=LQASAssessment.Status.SUBMITTED,
                )

                if selected_year:
                    reg_assessments = reg_assessments.filter(year=selected_year)
                if selected_period:
                    reg_assessments = reg_assessments.filter(period=selected_period)

                report_count = reg_assessments.count()
                avg_percentage = None
                if report_count > 0:
                    from django.db.models import Avg
                    avg_val = reg_assessments.aggregate(Avg("percentage"))["percentage__avg"]
                    if avg_val is not None:
                        avg_percentage = round(float(avg_val), 1)

                visible_regions.append({
                    "unit": region,
                    "facility_count": reg_facilities.count(),
                    "report_count": report_count,
                    "avg_percentage": avg_percentage,
                })

        # Build full organization tree for Ministry
        organization_tree = build_lqas_organization_tree(
            profile=profile,
            facility_queryset=accessible,
            selected_year=selected_year,
            selected_period=selected_period,
        )

        # Calculate high-level summary metrics
        total_facilities_count = accessible.count()
        filtered_submitted_qs = LQASAssessment.objects.filter(
            facility__in=accessible,
            status=LQASAssessment.Status.SUBMITTED,
        )
        if selected_year:
            filtered_submitted_qs = filtered_submitted_qs.filter(year=selected_year)
        if selected_period:
            filtered_submitted_qs = filtered_submitted_qs.filter(period=selected_period)

        total_audits_count = filtered_submitted_qs.count()
        audited_facilities_count = filtered_submitted_qs.values("facility_id").distinct().count()

        from django.db.models import Avg
        overall_avg_val = filtered_submitted_qs.aggregate(Avg("percentage"))["percentage__avg"]
        overall_avg_percentage = round(float(overall_avg_val), 1) if overall_avg_val is not None else None

        return render(
            request,
            "lqas/dashboard.html",
            {
                "profile": profile,
                "role": role,
                "regions": visible_regions,
                "organization_tree": organization_tree,
                "total_facilities": total_facilities_count,
                "audited_facilities_count": audited_facilities_count,
                "total_audits_count": total_audits_count,
                "overall_avg_percentage": overall_avg_percentage,
                "facility": None,
                **filter_options,
                **filter_params,
            },
        )

    # --------------------------------------------------------
    # REGION / SUBCITY / OTHER ORGANIZATIONAL USER
    # --------------------------------------------------------

    organization = getattr(
        profile,
        "organization",
        None,
    )

    if organization:

        query_params = request.GET.urlencode()
        url = f"/lqas/organization/{organization.pk}/"
        if query_params:
            url = f"{url}?{query_params}"
        return redirect(url)

    messages.error(
        request,
        "Your account does not have an organization assigned."
    )

    return render(
        request,
        "lqas/dashboard.html",
        {
            "profile": profile,
            "role": role,
            "regions": [],
            "facility": None,
            **filter_options,
            **filter_params,
        },
    )


# ============================================================
# ORGANIZATION DRILL-DOWN
# ============================================================

@login_required
def lqas_organization(request, unit_id):
    """
    Display an organization and its children/facilities with year and month filter,
    including the interactive hierarchical organization tree.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your user profile is not configured."
        )

        return redirect("accounts:login")

    unit = get_object_or_404(
        OrganizationUnit,
        pk=unit_id,
    )

    if not can_access_organization(
        profile,
        unit,
    ):

        messages.error(
            request,
            "You do not have permission to access this organization."
        )

        return redirect("lqas:dashboard")

    # Filter parameters
    filter_params = parse_lqas_filter_params(request)
    selected_year = filter_params["selected_year"]
    selected_period = filter_params["selected_period"]

    accessible_facilities = (
        get_accessible_facilities(profile)
    )

    filter_options = get_lqas_filter_options(accessible_facilities)

    child_units = get_visible_children(
        profile,
        unit,
    )

    children_data = []
    for child in child_units:
        descendant_ids = get_organization_tree_ids(child)
        child_facilities = accessible_facilities.filter(organization_id__in=descendant_ids)
        
        child_assessments = LQASAssessment.objects.filter(
            facility__in=child_facilities,
            status=LQASAssessment.Status.SUBMITTED,
        )
        if selected_year:
            child_assessments = child_assessments.filter(year=selected_year)
        if selected_period:
            child_assessments = child_assessments.filter(period=selected_period)
        
        child_report_count = child_assessments.count()
        child_avg_percentage = None
        if child_report_count > 0:
            from django.db.models import Avg
            avg_val = child_assessments.aggregate(Avg("percentage"))["percentage__avg"]
            if avg_val is not None:
                child_avg_percentage = round(float(avg_val), 1)

        children_data.append({
            "unit": child,
            "facility_count": child_facilities.count(),
            "report_count": child_report_count,
            "avg_percentage": child_avg_percentage,
        })

    # Facilities directly under this organization
    direct_facilities = (
        accessible_facilities.filter(
            organization=unit
        )
        .order_by("name")
    )

    facilities_data = []
    for fac in direct_facilities:
        fac_assessments = LQASAssessment.objects.filter(
            facility=fac,
            status=LQASAssessment.Status.SUBMITTED,
        )
        if selected_year:
            fac_assessments = fac_assessments.filter(year=selected_year)
        if selected_period:
            fac_assessments = fac_assessments.filter(period=selected_period)

        fac_report_count = fac_assessments.count()
        fac_latest = fac_assessments.order_by("-year", "-created_at").first()

        facilities_data.append({
            "facility": fac,
            "report_count": fac_report_count,
            "latest_assessment": fac_latest,
        })

    # Build hierarchical tree rooted at this unit
    unit_descendant_ids = get_organization_tree_ids(unit)
    unit_facilities = accessible_facilities.filter(organization_id__in=unit_descendant_ids)

    organization_tree = build_lqas_organization_tree(
        profile=profile,
        facility_queryset=unit_facilities,
        selected_year=selected_year,
        selected_period=selected_period,
        root_unit=unit,
    )

    # Summary metrics for this unit and its descendants
    total_facilities_count = unit_facilities.count()
    unit_submitted_qs = LQASAssessment.objects.filter(
        facility__in=unit_facilities,
        status=LQASAssessment.Status.SUBMITTED,
    )
    if selected_year:
        unit_submitted_qs = unit_submitted_qs.filter(year=selected_year)
    if selected_period:
        unit_submitted_qs = unit_submitted_qs.filter(period=selected_period)

    total_audits_count = unit_submitted_qs.count()
    audited_facilities_count = unit_submitted_qs.values("facility_id").distinct().count()

    from django.db.models import Avg
    unit_avg_val = unit_submitted_qs.aggregate(Avg("percentage"))["percentage__avg"]
    overall_avg_percentage = round(float(unit_avg_val), 1) if unit_avg_val is not None else None

    return render(
        request,
        "lqas/organization.html",
        {
            "profile": profile,
            "role": get_role(profile),
            "unit": unit,
            "children": children_data,
            "facilities": facilities_data,
            "organization_tree": organization_tree,
            "total_facilities": total_facilities_count,
            "audited_facilities_count": audited_facilities_count,
            "total_audits_count": total_audits_count,
            "overall_avg_percentage": overall_avg_percentage,
            **filter_options,
            **filter_params,
        },
    )


# ============================================================
# FACILITY REPORT LIST
# ============================================================

@login_required
def lqas_facility_reports(request, facility_id):
    """
    Show LQAS reports for one facility with year and month filter.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your user profile is not configured."
        )

        return redirect("accounts:login")

    facility = get_object_or_404(
        Facility,
        pk=facility_id,
    )

    if not can_access_facility(
        profile,
        facility,
    ):

        messages.error(
            request,
            "You do not have permission to access this facility."
        )

        return redirect("lqas:dashboard")

    role = get_role(profile)

    # Filter parameters
    filter_params = parse_lqas_filter_params(request)
    selected_year = filter_params["selected_year"]
    selected_period = filter_params["selected_period"]

    filter_options = get_lqas_filter_options(Facility.objects.filter(pk=facility.pk))

    reports = (
        LQASAssessment.objects.filter(
            facility=facility
        )
        .select_related(
            "facility",
            "created_by",
        )
    )

    if role != "FACILITY_USER":

        reports = reports.filter(
            status=LQASAssessment.Status.SUBMITTED
        )

    # Apply year & month / period filters
    if selected_year:
        reports = reports.filter(year=selected_year)

    if selected_period:
        reports = reports.filter(period=selected_period)

    reports = reports.order_by(
        "-year",
        "-created_at",
    )

    return render(
        request,
        "lqas/facility_reports.html",
        {
            "profile": profile,
            "role": role,
            "facility": facility,
            "reports": reports,
            **filter_options,
            **filter_params,
        },
    )


# ============================================================
# CREATE / SUBMIT LQAS
# ============================================================

@login_required
def lqas_create(request):
    """
    Facility user creates and submits an LQAS assessment.

    Exactly 12 rows are displayed.

    Blank rows are allowed.

    Partially completed rows are rejected.

    At least one completed row is required.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your user profile is not configured."
        )

        return redirect("accounts:login")

    role = get_role(profile)

    if role != "FACILITY_USER":

        messages.error(
            request,
            "Only facility users can create and submit LQAS."
        )

        return redirect("lqas:dashboard")

    facility = getattr(
        profile,
        "facility",
        None,
    )

    if not facility:

        messages.error(
            request,
            "No facility is assigned to your account."
        )

        return redirect("lqas:dashboard")

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        year = request.POST.get(
            "year",
            ""
        ).strip()

        period = request.POST.get(
            "period",
            ""
        ).strip()

        if not year:

            messages.error(
                request,
                "Please enter the year."
            )

            return render(
                request,
                "lqas/create.html",
                {
                    "facility": facility,
                    "rows": range(1, 13),
                },
            )

        if not period:

            messages.error(
                request,
                "Please select the reporting period."
            )

            return render(
                request,
                "lqas/create.html",
                {
                    "facility": facility,
                    "rows": range(1, 13),
                },
            )

        try:
            year = int(year)

        except (ValueError, TypeError):

            messages.error(
                request,
                "Year must be a valid number."
            )

            return render(
                request,
                "lqas/create.html",
                {
                    "facility": facility,
                    "rows": range(1, 13),
                },
            )

        # ----------------------------------------------------
        # Prevent duplicate reporting period
        # ----------------------------------------------------

        existing = LQASAssessment.objects.filter(
            facility=facility,
            year=year,
            period=period,
        ).exists()

        if existing:

            messages.error(
                request,
                "An LQAS report already exists for this facility, year and period."
            )

            return redirect(
                "lqas:facility_reports",
                facility_id=facility.pk,
            )

        # ----------------------------------------------------
        # Read exactly 12 rows
        # ----------------------------------------------------

        submitted_rows = []
        validation_errors = []

        for i in range(1, 13):

            name = request.POST.get(
                f"data_element_name_{i}",
                ""
            ).strip()

            tally = request.POST.get(
                f"tally_sheet_count_{i}",
                ""
            ).strip()

            register = request.POST.get(
                f"register_count_{i}",
                ""
            ).strip()

            report = request.POST.get(
                f"report_count_{i}",
                ""
            ).strip()

            # Completely blank row
            if (
                not name
                and not tally
                and not register
                and not report
            ):
                continue

            # Partially completed row
            if (
                not name
                or not tally
                or not register
                or not report
            ):

                validation_errors.append(
                    f"Row {i}: please complete the data element name and all three counts."
                )

                continue

            try:

                tally_value = int(tally)
                register_value = int(register)
                report_value = int(report)

            except (ValueError, TypeError):

                validation_errors.append(
                    f"Row {i}: counts must be whole numbers."
                )

                continue

            if (
                tally_value < 0
                or register_value < 0
                or report_value < 0
            ):

                validation_errors.append(
                    f"Row {i}: counts cannot be negative."
                )

                continue

            submitted_rows.append(
                {
                    "name": name,
                    "tally": tally_value,
                    "register": register_value,
                    "report": report_value,
                }
            )

        # ----------------------------------------------------
        # Validation errors
        # ----------------------------------------------------

        if validation_errors:

            for error in validation_errors:
                messages.error(
                    request,
                    error,
                )

            return render(
                request,
                "lqas/create.html",
                {
                    "facility": facility,
                    "rows": range(1, 13),
                },
            )

        # ----------------------------------------------------
        # At least one row
        # ----------------------------------------------------

        if not submitted_rows:

            messages.error(
                request,
                "Please complete at least one LQAS data element."
            )

            return render(
                request,
                "lqas/create.html",
                {
                    "facility": facility,
                    "rows": range(1, 13),
                },
            )

        # ----------------------------------------------------
        # Save assessment + responses
        # ----------------------------------------------------

        with transaction.atomic():

            assessment = LQASAssessment.objects.create(
                facility=facility,
                year=year,
                period=period,
                status=LQASAssessment.Status.SUBMITTED,
                created_by=request.user,
            )

            for row in submitted_rows:

                LQASResponse.objects.create(
                    assessment=assessment,
                    data_element_name=row["name"],

                    # IMPORTANT:
                    # These are the actual model field names.
                    tally_sheet=row["tally"],
                    register=row["register"],
                    report=row["report"],
                )

            assessment.calculate_result()

            assessment.save(
                update_fields=[
                    "matched_count",
                    "total_elements",
                    "percentage",
                    "updated_at",
                ],
            )

        messages.success(
            request,
            "LQAS report submitted successfully."
        )

        return redirect(
            "lqas:result",
            assessment_id=assessment.pk,
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    return render(
        request,
        "lqas/create.html",
        {
            "facility": facility,
            "rows": range(1, 13),
        },
    )


# ============================================================
# VIEW RESULT
# ============================================================

@login_required
def lqas_result(request, assessment_id):
    """
    Display one LQAS report.
    """

    profile = get_active_profile(request)

    if not profile:

        messages.error(
            request,
            "Your user profile is not configured."
        )

        return redirect("accounts:login")

    assessment = get_object_or_404(
        LQASAssessment.objects.select_related(
            "facility",
            "created_by",
        ),
        pk=assessment_id,
    )

    facility = assessment.facility

    if not can_access_facility(
        profile,
        facility,
    ):

        messages.error(
            request,
            "You do not have permission to view this report."
        )

        return redirect("lqas:dashboard")

    role = get_role(profile)

    if (
        role != "FACILITY_USER"
        and assessment.status
        != LQASAssessment.Status.SUBMITTED
    ):

        messages.error(
            request,
            "This report has not been submitted."
        )

        return redirect(
            "lqas:facility_reports",
            facility_id=facility.pk,
        )

    responses = (
        assessment.responses.all()
        .order_by("id")
    )

    return render(
        request,
        "lqas/result.html",
        {
            "profile": profile,
            "role": role,
            "assessment": assessment,
            "facility": facility,
            "responses": responses,
        },
    )


# ============================================================
# PRINT
# ============================================================

@login_required
def lqas_print(request, assessment_id):
    """
    Printer-friendly LQAS report.
    """

    profile = get_active_profile(request)

    if not profile:
        return redirect("accounts:login")

    assessment = get_object_or_404(
        LQASAssessment.objects.select_related(
            "facility",
            "created_by",
        ),
        pk=assessment_id,
    )

    if not can_access_facility(
        profile,
        assessment.facility,
    ):

        messages.error(
            request,
            "You do not have permission to print this report."
        )

        return redirect("lqas:dashboard")

    if (
        get_role(profile) != "FACILITY_USER"
        and assessment.status
        != LQASAssessment.Status.SUBMITTED
    ):

        messages.error(
            request,
            "Only submitted reports can be printed."
        )

        return redirect(
            "lqas:facility_reports",
            facility_id=assessment.facility.pk,
        )

    return render(
        request,
        "lqas/print.html",
        {
            "assessment": assessment,
            "facility": assessment.facility,
            "responses": (
                assessment.responses.all()
                .order_by("id")
            ),
        },
    )


# ============================================================
# EXPORT ACCESS HELPER
# ============================================================

def get_exportable_lqas_assessment(
    request,
    assessment_id,
):
    """
    Load an LQAS assessment and verify export permission.

    Facility users:
        Can export their own assessment.

    Higher-level users:
        Can export submitted assessments only.
    """

    profile = get_active_profile(request)

    if not profile:
        return None, None, redirect("accounts:login")

    assessment = get_object_or_404(
        LQASAssessment.objects.select_related(
            "facility",
            "created_by",
        ),
        pk=assessment_id,
    )

    if not can_access_facility(
        profile,
        assessment.facility,
    ):

        messages.error(
            request,
            "You do not have permission to export this report."
        )

        return (
            None,
            None,
            redirect("lqas:dashboard"),
        )

    role = get_role(profile)

    if (
        role != "FACILITY_USER"
        and assessment.status
        != LQASAssessment.Status.SUBMITTED
    ):

        messages.error(
            request,
            "Only submitted reports can be exported."
        )

        return (
            None,
            None,
            redirect(
                "lqas:facility_reports",
                facility_id=assessment.facility.pk,
            ),
        )

    return (
        profile,
        assessment,
        None,
    )


# ============================================================
# EXCEL EXPORT
# ============================================================

@login_required
def lqas_export_excel(request, assessment_id):
    """
    Export one LQAS report as a real Excel XLSX file.
    """

    profile, assessment, error_response = (
        get_exportable_lqas_assessment(
            request,
            assessment_id,
        )
    )

    if error_response:
        return error_response

    try:

        from openpyxl import Workbook
        from openpyxl.styles import (
            Alignment,
            Border,
            Font,
            PatternFill,
            Side,
        )
        from openpyxl.utils import get_column_letter

    except ImportError:

        messages.error(
            request,
            "Excel export requires openpyxl. "
            "Install it with: pip install openpyxl"
        )

        return redirect(
            "lqas:result",
            assessment_id=assessment.pk,
        )

    # --------------------------------------------------------
    # Make sure summary is current
    # --------------------------------------------------------

    assessment.calculate_result()

    # --------------------------------------------------------
    # Workbook
    # --------------------------------------------------------

    workbook = Workbook()

    worksheet = workbook.active
    worksheet.title = "LQAS Report"

    # --------------------------------------------------------
    # Styles
    # --------------------------------------------------------

    title_font = Font(
        bold=True,
        size=16,
    )

    header_font = Font(
        bold=True,
        size=11,
    )

    bold_font = Font(
        bold=True,
    )

    thin_side = Side(
        style="thin",
    )

    border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side,
    )

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9EAF7",
    )

    summary_fill = PatternFill(
        fill_type="solid",
        fgColor="E2F0D9",
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    worksheet.merge_cells(
        "A1:H1"
    )

    worksheet["A1"] = "EHIR - LQAS REPORT"

    worksheet["A1"].font = title_font
    worksheet["A1"].alignment = Alignment(
        horizontal="center",
        vertical="center",
    )

    worksheet.row_dimensions[1].height = 28

    # --------------------------------------------------------
    # Assessment information
    # --------------------------------------------------------

    info_rows = [
        ("Facility", assessment.facility.name),
        (
            "Facility Code",
            getattr(
                assessment.facility,
                "code",
                "",
            ),
        ),
        ("Year", assessment.year),
        ("Period", assessment.period),
        (
            "Status",
            assessment.get_status_display(),
        ),
        (
            "Matched",
            assessment.matched_count,
        ),
        (
            "Total Elements",
            assessment.total_elements,
        ),
        (
            "Accuracy",
            f"{assessment.percentage}%",
        ),
        (
            "Created By",
            assessment.created_by.get_full_name()
            or assessment.created_by.username,
        ),
        (
            "Created At",
            assessment.created_at.strftime(
                "%Y-%m-%d %H:%M"
            )
            if assessment.created_at
            else "",
        ),
    ]

    current_row = 3

    for label, value in info_rows:

        worksheet.cell(
            row=current_row,
            column=1,
            value=label,
        )

        worksheet.cell(
            row=current_row,
            column=1,
        ).font = bold_font

        worksheet.cell(
            row=current_row,
            column=2,
            value=value,
        )

        current_row += 1

    # --------------------------------------------------------
    # Summary section
    # --------------------------------------------------------

    current_row += 1

    summary_start_row = current_row

    worksheet.merge_cells(
        start_row=current_row,
        start_column=1,
        end_row=current_row,
        end_column=8,
    )

    worksheet.cell(
        row=current_row,
        column=1,
        value="LQAS DATA ELEMENT RESULTS",
    )

    worksheet.cell(
        row=current_row,
        column=1,
    ).font = header_font

    worksheet.cell(
        row=current_row,
        column=1,
    ).fill = summary_fill

    worksheet.cell(
        row=current_row,
        column=1,
    ).alignment = Alignment(
        horizontal="center",
    )

    current_row += 1

    # --------------------------------------------------------
    # Table header
    # --------------------------------------------------------

    headers = [
        "No.",
        "Data Element",
        "Tally Sheet",
        "Register",
        "Report",
        "Match",
        "Result",
        "Notes",
    ]

    for column_number, header in enumerate(
        headers,
        start=1,
    ):

        cell = worksheet.cell(
            row=current_row,
            column=column_number,
            value=header,
        )

        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    header_row = current_row
    current_row += 1

    # --------------------------------------------------------
    # Response rows
    # --------------------------------------------------------

    responses = (
        assessment.responses.all()
        .order_by("id")
    )

    for number, item in enumerate(
        responses,
        start=1,
    ):

        match_text = (
            "YES"
            if item.match
            else "NO"
        )

        result_text = (
            "Matched"
            if item.match
            else "Not Matched"
        )

        values = [
            number,
            item.data_element_name,
            item.tally_sheet
            if item.tally_sheet is not None
            else "",
            item.register
            if item.register is not None
            else "",
            item.report
            if item.report is not None
            else "",
            match_text,
            result_text,
            "",
        ]

        for column_number, value in enumerate(
            values,
            start=1,
        ):

            cell = worksheet.cell(
                row=current_row,
                column=column_number,
                value=value,
            )

            cell.border = border

            cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
            )

            if column_number in {
                1,
                3,
                4,
                5,
                6,
            }:

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

        current_row += 1

    last_data_row = current_row - 1

    # --------------------------------------------------------
    # Summary at bottom
    # --------------------------------------------------------

    current_row += 1

    worksheet.cell(
        row=current_row,
        column=1,
        value="Matched Elements",
    ).font = bold_font

    worksheet.cell(
        row=current_row,
        column=2,
        value=assessment.matched_count,
    )

    current_row += 1

    worksheet.cell(
        row=current_row,
        column=1,
        value="Total Elements",
    ).font = bold_font

    worksheet.cell(
        row=current_row,
        column=2,
        value=assessment.total_elements,
    )

    current_row += 1

    worksheet.cell(
        row=current_row,
        column=1,
        value="Overall Accuracy",
    ).font = bold_font

    worksheet.cell(
        row=current_row,
        column=2,
        value=f"{assessment.percentage}%",
    )

    # --------------------------------------------------------
    # Borders / styling
    # --------------------------------------------------------

    for row in worksheet.iter_rows(
        min_row=header_row,
        max_row=last_data_row,
        min_col=1,
        max_col=8,
    ):

        for cell in row:
            cell.border = border

    # --------------------------------------------------------
    # Column widths
    # --------------------------------------------------------

    widths = {
        "A": 8,
        "B": 50,
        "C": 16,
        "D": 16,
        "E": 16,
        "F": 14,
        "G": 18,
        "H": 25,
    }

    for column, width in widths.items():
        worksheet.column_dimensions[
            column
        ].width = width

    # --------------------------------------------------------
    # Freeze table header
    # --------------------------------------------------------

    worksheet.freeze_panes = (
        f"A{header_row + 1}"
    )

    # --------------------------------------------------------
    # Auto filter
    # --------------------------------------------------------

    if last_data_row >= header_row:

        worksheet.auto_filter.ref = (
            f"A{header_row}:H{last_data_row}"
        )

    # --------------------------------------------------------
    # Page setup
    # --------------------------------------------------------

    worksheet.page_setup.orientation = (
        "landscape"
    )

    worksheet.page_setup.paperSize = (
        worksheet.PAPERSIZE_A4
    )

    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0

    worksheet.sheet_properties.pageSetUpPr.fitToPage = True

    # --------------------------------------------------------
    # HTTP response
    # --------------------------------------------------------

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

    facility_code = (
        getattr(
            assessment.facility,
            "code",
            assessment.facility.pk,
        )
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="LQAS_%s_%s_%s.xlsx"'
        % (
            facility_code,
            assessment.year,
            assessment.period,
        )
    )

    workbook.save(response)

    return response


# ============================================================
# PDF EXPORT
# ============================================================

@login_required
def lqas_export_pdf(request, assessment_id):
    """
    Export one LQAS report as a formatted PDF.
    """

    profile, assessment, error_response = (
        get_exportable_lqas_assessment(
            request,
            assessment_id,
        )
    )

    if error_response:
        return error_response

    try:

        from xml.sax.saxutils import escape

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import (
            ParagraphStyle,
            getSampleStyleSheet,
        )
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

    except ImportError:

        messages.error(
            request,
            "PDF export requires reportlab. "
            "Install it with: pip install reportlab"
        )

        return redirect(
            "lqas:result",
            assessment_id=assessment.pk,
        )

    # --------------------------------------------------------
    # Make sure summary is current
    # --------------------------------------------------------

    assessment.calculate_result()

    # --------------------------------------------------------
    # Safe PDF text
    # --------------------------------------------------------

    def pdf_text(value):
        """
        Safely escape dynamic text before sending it
        to a ReportLab Paragraph.
        """

        if value is None:
            value = ""

        return escape(
            str(value)
        ).replace(
            "\n",
            "<br/>",
        )

    # --------------------------------------------------------
    # HTTP response
    # --------------------------------------------------------

    response = HttpResponse(
        content_type="application/pdf"
    )

    facility_code = (
        getattr(
            assessment.facility,
            "code",
            assessment.facility.pk,
        )
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="LQAS_%s_%s_%s.pdf"'
        % (
            facility_code,
            assessment.year,
            assessment.period,
        )
    )

    # --------------------------------------------------------
    # PDF document
    # --------------------------------------------------------

    document = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "LQASTitle",
        parent=styles["Title"],
        fontSize=17,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    normal_style = ParagraphStyle(
        "LQASNormal",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    small_style = ParagraphStyle(
        "LQASSmall",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
    )

    header_style = ParagraphStyle(
        "LQASHeader",
        parent=styles["Normal"],
        fontSize=8,
        leading=9,
        alignment=TA_CENTER,
    )

    elements = []

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "EHIR - LQAS REPORT",
            title_style,
        )
    )

    elements.append(
        Spacer(1, 4)
    )

    # --------------------------------------------------------
    # Information table
    # --------------------------------------------------------

    info_data = [
        [
            Paragraph(
                "<b>Facility</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.facility.name
                ),
                normal_style,
            ),
            Paragraph(
                "<b>Facility Code</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    getattr(
                        assessment.facility,
                        "code",
                        "",
                    )
                ),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Year</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.year
                ),
                normal_style,
            ),
            Paragraph(
                "<b>Period</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.period
                ),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Status</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.get_status_display()
                ),
                normal_style,
            ),
            Paragraph(
                "<b>Created By</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.created_by.get_full_name()
                    or assessment.created_by.username
                ),
                normal_style,
            ),
        ],
    ]

    info_table = Table(
        info_data,
        colWidths=[
            28 * mm,
            67 * mm,
            28 * mm,
            67 * mm,
        ],
    )

    info_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.grey,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.whitesmoke,
                ),
                (
                    "BACKGROUND",
                    (2, 0),
                    (2, -1),
                    colors.whitesmoke,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    elements.append(info_table)

    elements.append(
        Spacer(1, 10)
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_data = [
        [
            Paragraph(
                "<b>Total Elements</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.total_elements
                ),
                normal_style,
            ),
            Paragraph(
                "<b>Matched</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    assessment.matched_count
                ),
                normal_style,
            ),
            Paragraph(
                "<b>Accuracy</b>",
                normal_style,
            ),
            Paragraph(
                pdf_text(
                    f"{assessment.percentage}%"
                ),
                normal_style,
            ),
        ]
    ]

    summary_table = Table(
        summary_data,
        colWidths=[
            30 * mm,
            25 * mm,
            25 * mm,
            25 * mm,
            25 * mm,
            30 * mm,
        ],
    )

    summary_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, 0),
                    colors.whitesmoke,
                ),
                (
                    "BACKGROUND",
                    (2, 0),
                    (2, 0),
                    colors.whitesmoke,
                ),
                (
                    "BACKGROUND",
                    (4, 0),
                    (4, 0),
                    colors.whitesmoke,
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    elements.append(summary_table)

    elements.append(
        Spacer(1, 10)
    )

    # --------------------------------------------------------
    # LQAS response table
    # --------------------------------------------------------

    table_data = [
        [
            Paragraph(
                "<b>No.</b>",
                header_style,
            ),
            Paragraph(
                "<b>Data Element</b>",
                header_style,
            ),
            Paragraph(
                "<b>Tally Sheet</b>",
                header_style,
            ),
            Paragraph(
                "<b>Register</b>",
                header_style,
            ),
            Paragraph(
                "<b>Report</b>",
                header_style,
            ),
            Paragraph(
                "<b>Match</b>",
                header_style,
            ),
        ]
    ]

    responses = (
        assessment.responses.all()
        .order_by("id")
    )

    for number, item in enumerate(
        responses,
        start=1,
    ):

        table_data.append(
            [
                Paragraph(
                    pdf_text(number),
                    small_style,
                ),
                Paragraph(
                    pdf_text(
                        item.data_element_name
                    ),
                    small_style,
                ),
                Paragraph(
                    pdf_text(
                        item.tally_sheet
                        if item.tally_sheet is not None
                        else ""
                    ),
                    small_style,
                ),
                Paragraph(
                    pdf_text(
                        item.register
                        if item.register is not None
                        else ""
                    ),
                    small_style,
                ),
                Paragraph(
                    pdf_text(
                        item.report
                        if item.report is not None
                        else ""
                    ),
                    small_style,
                ),
                Paragraph(
                    pdf_text(
                        "YES"
                        if item.match
                        else "NO"
                    ),
                    small_style,
                ),
            ]
        )

    result_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            12 * mm,
            95 * mm,
            25 * mm,
            25 * mm,
            25 * mm,
            20 * mm,
        ],
    )

    result_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.black,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (0, -1),
                    "CENTER",
                ),
                (
                    "ALIGN",
                    (2, 1),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
            ]
        )
    )

    elements.append(result_table)

    elements.append(
        Spacer(1, 12)
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            (
                f"<b>Overall Result:</b> "
                f"{assessment.matched_count} "
                f"of {assessment.total_elements} "
                f"data elements matched."
            ),
            normal_style,
        )
    )

    elements.append(
        Paragraph(
            (
                f"<b>Accuracy:</b> "
                f"{pdf_text(assessment.percentage)}%"
            ),
            normal_style,
        )
    )

    elements.append(
        Spacer(1, 8)
    )

    elements.append(
        Paragraph(
            (
                "<b>Generated by EHIR Health Information System</b>"
            ),
            small_style,
        )
    )

    document.build(elements)

    return response
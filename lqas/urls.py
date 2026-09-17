from django.urls import path

from . import views


app_name = "lqas"


urlpatterns = [
    # Main LQAS page
    path("", views.lqas_dashboard, name="dashboard"),

    # Organization drill-down
    path(
        "organization/<int:unit_id>/",
        views.lqas_organization,
        name="organization",
    ),

    # Facility reports
    path(
        "facility/<int:facility_id>/",
        views.lqas_facility_reports,
        name="facility_reports",
    ),

    # Facility creates/submits LQAS
    path(
        "new/",
        views.lqas_create,
        name="create",
    ),

    # Individual report
    path(
        "report/<int:assessment_id>/",
        views.lqas_result,
        name="result",
    ),

    # Print
    path(
        "report/<int:assessment_id>/print/",
        views.lqas_print,
        name="print",
    ),

    # Excel
    path(
        "report/<int:assessment_id>/excel/",
        views.lqas_export_excel,
        name="export_excel",
    ),

    # PDF
    path(
        "report/<int:assessment_id>/pdf/",
        views.lqas_export_pdf,
        name="export_pdf",
    ),
]
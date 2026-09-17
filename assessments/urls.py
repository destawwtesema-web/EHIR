from django.urls import path

from . import views


app_name = "assessments"


urlpatterns = [

    # =========================================================
    # ASSESSMENT DASHBOARD
    # =========================================================

    path(
        "",
        views.dashboard,
        name="dashboard",
    ),

    # =========================================================
    # START NEW ASSESSMENT
    # =========================================================

    path(
        "start/",
        views.assessment_start,
        name="start",
    ),

    # =========================================================
    # ASSESSMENT DETAIL
    # =========================================================

    path(
        "<int:assessment_id>/",
        views.assessment_detail,
        name="assessment_detail",
    ),

    # =========================================================
    # REVIEW ASSESSMENT
    # =========================================================

    path(
        "<int:assessment_id>/review/",
        views.assessment_review,
        name="assessment_review",
    ),

    # =========================================================
    # APPROVE ASSESSMENT
    # =========================================================

    path(
        "<int:assessment_id>/approve/",
        views.assessment_approve,
        name="assessment_approve",
    ),

    # =========================================================
    # ASSESSMENT SUCCESS
    # =========================================================

    path(
        "<int:assessment_id>/success/",
        views.assessment_success,
        name="assessment_success",
    ),

    # =========================================================
    # EXPORT ASSESSMENT TO PDF
    # =========================================================

    path(
        "export/<int:assessment_id>/pdf/",
        views.export_assessment_pdf,
        name="export_pdf",
    ),

    # =========================================================
    # EXPORT ASSESSMENT TO EXCEL
    # =========================================================

    path(
        "export/<int:assessment_id>/excel/",
        views.export_assessment_excel,
        name="export_excel",
    ),
]
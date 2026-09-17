from django.contrib import admin
from django.urls import include, path


urlpatterns = [

    # =========================================================
    # DJANGO ADMIN
    # URL: /admin/
    # =========================================================
    path(
        "admin/",
        admin.site.urls,
    ),

    # =========================================================
    # ACCOUNTS
    # URL: /accounts/
    # =========================================================
    path(
        "accounts/",
        include("accounts.urls"),
    ),

    # =========================================================
    # ASSESSMENTS
    # URL: /assessments/
    # =========================================================
    path(
        "assessments/",
        include("assessments.urls"),
    ),

    # =========================================================
    # LQAS
    # URL: /lqas/
    # =========================================================
    path(
        "lqas/",
        include("lqas.urls"),
    ),

    # =========================================================
    # DASHBOARD APP
    # URL: /dashboard/
    # =========================================================
    path(
        "dashboard/",
        include("dashboard.urls"),
    ),
      path(
        "feedback/",
        include("feedback.urls"),
    ),

    # =========================================================
    # CORE / HOME PAGE
    # URL: /
    # =========================================================
    path(
        "",
        include("core.urls"),
    ),

]
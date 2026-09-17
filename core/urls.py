from django.urls import path

from . import views


app_name = "core"


urlpatterns = [

    # =========================================================
    # HOME
    # URL: /
    # =========================================================
    path(
        "",
        views.home,
        name="home",
    ),

    # =========================================================
    # ANALYTICS
    # URL: /analytics/
    # =========================================================
    path(
        "analytics/",
        views.analytics_dashboard,
        name="analytics",
    ),

    # =========================================================
    # NOTIFICATIONS
    # URL: /notifications/
    # =========================================================
    path(
        "notifications/",
        views.notifications_dashboard,
        name="notifications",
    ),

    # =========================================================
    # FEEDBACK
    # URL: /feedback/
    # =========================================================
    path(
        "feedback/",
        views.feedback_dashboard,
        name="feedback",
    ),
]
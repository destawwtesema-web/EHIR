from django.urls import path

from . import views


app_name = "dashboard"


urlpatterns = [

    # Main EHIRS Home
    path(
        "",
        views.dashboard_home,
        name="home",
    ),

    # Ministry dashboard
    path(
        "ministry/",
        views.ministry_dashboard,
        name="ministry",
    ),

    # Regional dashboard
    path(
        "regional/",
        views.regional_dashboard,
        name="regional",
    ),

    # Sub-city dashboard
    path(
        "subcity/",
        views.subcity_dashboard,
        name="subcity",
    ),

    # Facility dashboard
    path(
        "facility/",
        views.facility_dashboard,
        name="facility",
    ),
]

from django.urls import path

from . import views


app_name = "accounts"


urlpatterns = [

    # ======================================================
    # LOGIN / LOGOUT
    # ======================================================

    path(
        "",
        views.EHIRSLoginView.as_view(),
        name="login",
    ),

    path(
        "login/",
        views.EHIRSLoginView.as_view(),
        name="login_page",
    ),

    path(
        "logout/",
        views.LogoutView.as_view(
            next_page="accounts:login"
        ),
        name="logout",
    ),

    # ======================================================
    # USER MANAGEMENT
    # ======================================================

    path(
        "users/",
        views.user_management,
        name="user_management",
    ),

    path(
        "users/create/",
        views.user_create,
        name="user_create",
    ),

    path(
        "users/<int:profile_id>/edit/",
        views.user_edit,
        name="user_edit",
    ),

    path(
        "users/<int:profile_id>/toggle/",
        views.user_toggle_active,
        name="user_toggle_active",
    ),

    path(
        "users/<int:profile_id>/reset-password/",
        views.user_reset_password,
        name="user_reset_password",
    ),
]

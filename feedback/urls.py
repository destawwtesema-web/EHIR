from django.urls import path

from . import views


app_name = "feedback"


urlpatterns = [
    path(
        "",
        views.feedback_dashboard,
        name="dashboard",
    ),

    path(
        "new/",
        views.feedback_create,
        name="create",
    ),

    path(
        "<int:feedback_id>/",
        views.feedback_detail,
        name="detail",
    ),

    path(
        "<int:feedback_id>/reply/",
        views.feedback_reply,
        name="reply",
    ),

    path(
        "<int:feedback_id>/status/",
        views.feedback_update_status,
        name="update_status",
    ),
]
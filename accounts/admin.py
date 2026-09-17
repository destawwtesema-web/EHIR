
from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "organization",
        "facility",
        "active",
    )

    list_filter = (
        "role",
        "active",
        "organization",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )

    autocomplete_fields = (
        "user",
        "organization",
        "facility",
    )

    list_select_related = (
        "user",
        "organization",
        "facility",
    )

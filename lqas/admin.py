from django.contrib import admin

from .models import (
    LQASAssessment,
    LQASResponse,
)


class LQASResponseInline(admin.TabularInline):

    model = LQASResponse

    extra = 0

    fields = (
        "data_element_name",
        "tally_sheet",
        "register",
        "report",
        "match",
    )

    readonly_fields = (
        "match",
    )


@admin.register(LQASAssessment)
class LQASAssessmentAdmin(admin.ModelAdmin):

    list_display = (
        "facility",
        "year",
        "period",
        "status",
        "matched_count",
        "total_elements",
        "percentage",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "year",
        "period",
    )

    search_fields = (
        "facility__name",
        "facility__code",
        "created_by__username",
    )

    readonly_fields = (
        "matched_count",
        "total_elements",
        "percentage",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "facility",
        "created_by",
    )

    inlines = (
        LQASResponseInline,
    )

    ordering = (
        "-year",
        "-created_at",
    )


@admin.register(LQASResponse)
class LQASResponseAdmin(admin.ModelAdmin):

    list_display = (
        "assessment",
        "data_element_name",
        "tally_sheet",
        "register",
        "report",
        "match",
    )

    list_filter = (
        "match",
        "assessment__year",
        "assessment__status",
    )

    search_fields = (
        "data_element_name",
        "assessment__facility__name",
        "assessment__facility__code",
    )

    readonly_fields = (
        "match",
    )

    ordering = (
        "assessment",
        "id",
    )
from django.contrib import admin

from .models import (
    AssessmentSection,
    AssessmentThematicArea,
    AssessmentIndicator,
    IndicatorOption,
    AssessmentPeriod,
    Assessment,
    AssessmentResponse,
)


class IndicatorOptionInline(admin.TabularInline):
    model = IndicatorOption
    extra = 2
    fields = ("code", "label", "score", "order", "active")


@admin.register(AssessmentSection)
class AssessmentSectionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "weight", "order", "active")
    list_filter = ("active",)
    search_fields = ("code", "name")
    ordering = ("order", "code")


@admin.register(AssessmentThematicArea)
class AssessmentThematicAreaAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "section",
        "maximum_score",
        "order",
        "active",
    )
    list_filter = ("section", "active")
    search_fields = ("code", "name")
    ordering = ("section", "order")


@admin.register(AssessmentIndicator)
class AssessmentIndicatorAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "question",
        "thematic_area",
        "response_type",
        "calculation_type",
        "maximum_score",
        "order",
        "active",
    )

    list_filter = (
        "thematic_area__section",
        "thematic_area",
        "response_type",
        "calculation_type",
        "active",
    )

    search_fields = (
        "code",
        "question",
        "help_text",
    )

    ordering = (
        "thematic_area",
        "order",
    )

    autocomplete_fields = ("thematic_area",)

    inlines = [IndicatorOptionInline]


@admin.register(IndicatorOption)
class IndicatorOptionAdmin(admin.ModelAdmin):
    list_display = (
        "indicator",
        "code",
        "label",
        "score",
        "order",
        "active",
    )

    list_filter = (
        "active",
        "indicator__thematic_area__section",
    )

    search_fields = (
        "indicator__code",
        "indicator__question",
        "code",
        "label",
    )

    ordering = (
        "indicator",
        "order",
    )

    autocomplete_fields = ("indicator",)


@admin.register(AssessmentPeriod)
class AssessmentPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "year",
        "name",
        "period_type",
        "period_number",
        "start_month",
        "end_month",
        "active",
    )

    list_filter = (
        "year",
        "period_type",
        "active",
    )

    search_fields = ("name",)

    ordering = (
        "-year",
        "period_type",
        "period_number",
    )


class AssessmentResponseInline(admin.TabularInline):
    model = AssessmentResponse
    extra = 0
    readonly_fields = (
        "calculated_score",
        "created_at",
        "updated_at",
    )


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "facility",
        "period",
        "status",
        "total_score",
        "created_by",
        "created_at",
    )

    list_filter = (
        "status",
        "period__year",
        "period__period_type",
    )

    search_fields = (
        "facility__name",
        "facility__code",
    )

    readonly_fields = (
        "total_score",
        "created_at",
        "updated_at",
        "submitted_at",
        "reviewed_at",
        "approved_at",
    )

    autocomplete_fields = (
        "facility",
        "period",
        "created_by",
    )

    inlines = [AssessmentResponseInline]


@admin.register(AssessmentResponse)
class AssessmentResponseAdmin(admin.ModelAdmin):
    list_display = (
        "assessment",
        "indicator",
        "selected_option",
        "numeric_value",
        "numerator",
        "denominator",
        "calculated_score",
    )

    list_filter = (
        "indicator__thematic_area__section",
        "indicator__thematic_area",
    )

    search_fields = (
        "assessment__facility__name",
        "indicator__code",
        "indicator__question",
    )

    readonly_fields = (
        "calculated_score",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "assessment",
        "indicator",
        "selected_option",
    )
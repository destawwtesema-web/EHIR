from django.contrib import admin
from .models import OrganizationUnit, Facility


@admin.register(OrganizationUnit)
class OrganizationUnitAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "code",
        "unit_type",
        "parent",
        "active",
    )

    list_filter = (
        "unit_type",
        "active",
    )

    search_fields = (
        "name",
        "code",
    )

    ordering = (
        "name",
    )

    autocomplete_fields = (
        "parent",
    )


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "code",
        "facility_type",
        "organization",
        "active",
    )

    list_filter = (
        "facility_type",
        "active",
    )

    search_fields = (
        "name",
        "code",
    )

    ordering = (
        "name",
    )

    autocomplete_fields = (
        "organization",
    )
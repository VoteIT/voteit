from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.components.models import MeetingComponent
from voteit.components.models import OrganisationComponent


@admin.register(MeetingComponent)
class MeetingComponentAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    autocomplete_fields = ("meeting",)
    list_display = (
        "meeting",
        "component_name",
        "state",
        "is_valid"
        # "meeting__organisation",
    )
    list_filter = (
        "state",
        "component_name",
        "meeting__organisation",
    )
    search_fields = (
        "component_name",
        "meeting__title",
    )


@admin.register(OrganisationComponent)
class OrganisationComponentAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    autocomplete_fields = ("organisation",)
    list_display = (
        "organisation",
        "component_name",
        "state",
        "is_valid",
    )
    list_filter = (
        "organisation",
        "component_name",
    )

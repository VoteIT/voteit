from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib import admin

from voteit.components.models import MeetingComponent
from voteit.components.models import OrganisationComponent

if TYPE_CHECKING:
    from voteit.components.abcs import Component


class ComponentMixin:
    @admin.display(description="Settings valid?", boolean=True)
    def is_valid(self, obj: Component):
        return obj.is_valid

    @admin.display(description="Enabled?", boolean=True)
    def component_enabled(self, obj: Component):
        return obj.enabled


@admin.register(MeetingComponent)
class MeetingComponentAdmin(ComponentMixin, admin.ModelAdmin):
    autocomplete_fields = ("meeting",)
    list_display = (
        "meeting",
        "component_name",
        "is_valid",
        "component_enabled",
    )
    list_filter = (
        "meeting__organisation",
        "component_name",
        "enabled",
    )
    search_fields = (
        "component_name",
        "meeting__title",
    )


@admin.register(OrganisationComponent)
class OrganisationComponentAdmin(ComponentMixin, admin.ModelAdmin):
    autocomplete_fields = ("organisation",)
    list_display = (
        "organisation",
        "component_name",
        "is_valid",
        "component_enabled",
    )
    list_filter = (
        "organisation",
        "component_name",
        "enabled",
    )

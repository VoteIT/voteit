from django.contrib import admin
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.template import loader
from django.urls import reverse
from dolly.core import LiveCloner
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.components.models import MeetingComponent
from voteit.components.models import OrganisationComponent
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.utils import clone_meeting
from voteit.meeting.utils import collect_meeting
from voteit.meeting.utils import get_default_models_ignored_on_clone
from voteit.proposal.models import Proposal


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
    # fields =
    # exclude = ("mentions",)


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
    # search_fields = ("component_name",)

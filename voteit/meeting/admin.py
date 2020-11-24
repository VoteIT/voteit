from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.proposal.models import Proposal

from .models import Meeting, MeetingRoles


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    fields = "title", "order"
    extra = 1


@admin.register(Meeting)
class MeetingAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    # fields = ("title", )
    autocomplete_fields = ("organisation",)
    list_display = (
        "title",
        "ai_count",
        "proposal_count",
        "state",
        "start_time",
        "end_time",
    )
    list_filter = "organisation", "state"
    search_fields = ("title",)
    inlines = (AgendaItemInline,)

    def ai_count(self, obj: Meeting):
        return obj.agenda_items.count()

    ai_count.short_description = _("Agenda items")

    def proposal_count(self, obj: Meeting):
        return Proposal.objects.filter(agenda_item__meeting=obj).count()

    proposal_count.short_description = _("Proposals")


@admin.register(MeetingRoles)
class MeetingRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "assigned", "user", "context"

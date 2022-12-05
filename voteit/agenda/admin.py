from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib import admin
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.meeting.admin import MeetingAdminMixin

if TYPE_CHECKING:
    from voteit.core.abcs import AgendaItemContext


@admin.register(AgendaItem)
class AgendaAdmin(MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = (
        "title",
        "meeting_link",
        "proposal_count",
        "state",
    )
    list_filter = (
        "state",
        "meeting__organisation",
    )
    autocomplete_fields = (
        "meeting",
        "mentions",
    )
    search_fields = (
        "title",
        "body",
        "meeting__title",
    )
    exclude = ("order",)

    @admin.display(description="Proposals")
    def proposal_count(self, obj: AgendaItem):
        return obj.proposals.count()


class AgendaItemAdminMixin:
    @admin.display(description="Agenda item")
    def agenda_item_link(self, obj: AgendaItemContext):
        if obj.agenda_item:
            viewname = "admin:agenda_agendaitem_change"
            try:
                link = reverse(viewname, args=[obj.agenda_item.pk])
            except NoReverseMatch:
                return "%s" % obj.agenda_item
            return format_html('<a href="{}">{}</a>', link, obj.agenda_item)
        return "-"

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.admin import AgendaItemAdminMixin
from voteit.meeting.admin import MeetingAdminMixin
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument


@admin.register(Proposal)
class ProposalAdmin(
    AgendaItemAdminMixin, MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin
):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting_link",
        "agenda_item_link",
        "author",
        "meeting_group",
    )
    list_filter = (
        "state",
        "author__organisation",
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
        "author__first_name",
        "author__last_name",
        "author__userid",
        "meeting_group__groupid",
        "meeting_group__title",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
        "mentions",
    )
    exclude = ("state",)

    def agenda_item(self, obj):
        raise Exception("bla")


@admin.register(DiffProposal)
class DiffProposalAdmin(ProposalAdmin):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting_link",
        "agenda_item_link",
        "author",
        "meeting_group",
    )
    list_filter = (
        "state",
        "author__organisation",
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
        "author__first_name",
        "author__last_name",
        "author__userid",
        "meeting_group__groupid",
        "meeting_group__title",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
        "mentions",
    )
    exclude = ("state",)


@admin.register(TextDocument)
class TextDocumentAdmin(MeetingAdminMixin, AgendaItemAdminMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "meeting_link",
        "agenda_item_link",
        "base_tag",
    )
    list_filter = ("agenda_item__meeting__organisation",)
    search_fields = (
        "body",
        "base_tag",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = ("agenda_item",)

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument


@admin.register(Proposal)
class ProposalAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting",
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


@admin.register(DiffProposal)
class DiffProposalAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = (
        "prop_id",
        "__str__",
        "state",
        "meeting",
        "agenda_item",
        "author",
    )
    list_filter = (
        "state",
        "agenda_item",
        "agenda_item__meeting",
        "author",
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
    )
    exclude = ("state",)


@admin.register(TextDocument)
class TextDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "meeting",
        "agenda_item",
        "base_tag",
    )
    list_filter = (
        "agenda_item",
        "agenda_item__meeting",
    )
    search_fields = (
        "body",
        "base_tag",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = ("agenda_item",)

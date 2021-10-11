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

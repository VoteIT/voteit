from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.proposal.models import Proposal


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
        # "group",
    )
    list_filter = (
        "state",
        "agenda_item",
        "agenda_item__meeting",
        "author",  # "group"
    )
    search_fields = (
        "body",
        "prop_id",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    exclude = ("state",)

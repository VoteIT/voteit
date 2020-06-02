from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.proposal.models import Proposal


@admin.register(Proposal)
class ProposalAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = 'title', 'prop_id', 'state',
    list_filter = 'state', 'agenda_item',
    search_fields = 'title', 'body', 'agenda_item__title', 'agenda_item__meeting__title'
    exclude = 'state',

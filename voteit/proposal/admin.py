from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.proposal.models import Proposal


@admin.register(Proposal)
class ProposalAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]

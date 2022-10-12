from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem


@admin.register(AgendaItem)
class AgendaAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = (
        "title",
        "meeting",
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

    def proposal_count(self, obj: AgendaItem):
        return obj.proposals.count()

    proposal_count.short_description = "Proposals"

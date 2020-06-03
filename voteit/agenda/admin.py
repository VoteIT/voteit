from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem


@admin.register(AgendaItem)
class AgendaAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = 'title', 'proposal_count', 'state',
    list_filter = 'state', 'meeting',
    autocomplete_fields = 'meeting',
    search_fields = 'title', 'body',
    exclude = 'order',

    def proposal_count(self, obj: AgendaItem):
        return obj.proposals.count()
    proposal_count.short_description = _('Proposals')

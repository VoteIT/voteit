from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem


@admin.register(AgendaItem)
class AgendaAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]

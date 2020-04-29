from django.contrib import admin

from voteit.agenda.models import AgendaItem


@admin.register(AgendaItem)
class AgendaAdmin(admin.ModelAdmin):
    pass

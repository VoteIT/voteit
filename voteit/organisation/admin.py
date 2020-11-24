from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from voteit.organisation.models import Organisation


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    #autocomplete_fields = 'managers', 'meeting_creators',
    search_fields = 'title',
    list_display = 'title', 'meeting_count',

    def meeting_count(self, obj: Organisation):
        return obj.meetings.count()
    meeting_count.short_description = _('Meetings')

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.bug_reports.models import BugReport


@admin.register(BugReport)
class BugReportAdmin(FSMTransitionMixin, admin.ModelAdmin):
    list_display = "state", "function", "user", "organisation",
    list_filter = "state", "function", "user__organisation", "meeting", "created",
    search_fields = "user__userid", "user__first_name", "user__last_name", "meeting__title",

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in obj._meta.fields] + \
               [field.name for field in obj._meta.many_to_many]

    def organisation(self, instance: BugReport):
        return instance.user.organisation

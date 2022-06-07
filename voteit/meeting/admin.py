from django.contrib import admin
from django.db import transaction
from django.http import HttpResponse
from django.template import loader
from dolly.core import LiveCloner
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.utils import collect_meeting
from voteit.meeting.utils import get_default_models_ignored_on_clone
from voteit.proposal.models import Proposal


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    fields = "title", "order"
    extra = 1


@admin.register(Meeting)
class MeetingAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    # fields = ("title", )
    autocomplete_fields = ("organisation",)
    list_display = (
        "title",
        "ai_count",
        "proposal_count",
        "state",
        "start_time",
        "end_time",
    )
    list_filter = "organisation", "state"
    search_fields = ("title",)
    inlines = (AgendaItemInline,)
    actions = ["report_clone_meeting"]
    exclude = ("mentions",)

    def ai_count(self, obj: Meeting):
        return obj.agenda_items.count()

    ai_count.short_description = "Agenda items"

    def proposal_count(self, obj: Meeting):
        return Proposal.objects.filter(agenda_item__meeting=obj).count()

    proposal_count.short_description = "Proposals"

    def report_clone_meeting(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly 1 to report",
                self.ERROR,
            )
        exclude_models = get_default_models_ignored_on_clone()
        meeting = queryset.first()
        data = collect_meeting(meeting, exclude=exclude_models)
        cloner = LiveCloner(data=data)
        cloner.logging_enabled = True
        with transaction.atomic(durable=True):
            cloner()
            transaction.set_rollback(True)
        template = loader.get_template("dolly/log.html")
        context = {"log": cloner.log, "title": "Dry-run clone report"}
        return HttpResponse(template.render(context, request))


@admin.register(MeetingRoles)
class MeetingRolesAdmin(admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "assigned", "context"
    list_filter = (
        "context",
        "user",
        "user__organisation",
    )
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )


@admin.register(MeetingGroup)
class MeetingGroupAdmin(admin.ModelAdmin):
    autocomplete_fields = ("meeting", "members")
    list_display = ("title", "meeting", "member_count")
    list_filter = ("meeting", "members")
    search_fields = ("title",)
    exclude = ("mentions",)

    def member_count(self, group: MeetingGroup):
        return group.members.count()

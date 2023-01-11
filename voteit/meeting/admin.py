from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.template import loader
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html

from dolly.core import LiveCloner
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.utils import clone_meeting
from voteit.meeting.utils import collect_meeting
from voteit.meeting.utils import get_default_models_ignored_on_clone
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from voteit.core.abcs import MeetingContext


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    fields = "title", "order"
    extra = 1


@admin.register(Meeting)
class MeetingAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
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
    actions = ["report_clone_meeting", "clone_meeting"]
    exclude = ("mentions",)

    @admin.display(description="Agenda items")
    def ai_count(self, obj: Meeting):
        return obj.agenda_items.count()

    @admin.display(description="Proposals")
    def proposal_count(self, obj: Meeting):
        return Proposal.objects.filter(agenda_item__meeting=obj).count()

    def report_clone_meeting(self, request, queryset):
        from voteit.speaker.models import SpeakerListSystem

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
        cloner.add_clear_attrs(SpeakerListSystem, "active_list")
        cloner.add_clear_attrs(Meeting, "participants")
        cloner.logging_enabled = True
        with transaction.atomic(durable=True):
            cloner()
            transaction.set_rollback(True)
        template = loader.get_template("dolly/log.html")
        context = {"log": cloner.log, "title": "Dry-run clone report"}
        return HttpResponse(template.render(context, request))

    def clone_meeting(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly 1 to clone",
                self.ERROR,
            )
        meeting = queryset.first()
        with transaction.atomic(durable=True):
            cloned_meeting = clone_meeting(meeting, user=request.user)
        url = reverse(
            "admin:meeting_meeting_change", kwargs={"object_id": cloned_meeting.pk}
        )
        return HttpResponseRedirect(url)


class MeetingAdminMixin:
    @admin.display(description="Meeting")
    def meeting_link(self, obj: MeetingContext):
        if obj.meeting:
            viewname = "admin:meeting_meeting_change"
            try:
                link = reverse(viewname, args=[obj.meeting.pk])
            except NoReverseMatch:
                return "%s" % obj.meeting
            return format_html('<a href="{}">{}</a>', link, obj.meeting)
        return "-"


@admin.register(MeetingRoles)
class MeetingRolesAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "assigned", "meeting_link"
    list_filter = ("user__organisation",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )


@admin.register(MeetingGroup)
class MeetingGroupAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = (
        "meeting",
        "members",
    )
    list_display = (
        "title",
        "meeting_link",
        "votes",
        "member_count",
    )
    list_filter = ("meeting__organisation",)
    search_fields = ("title", "meeting__title")
    exclude = ("mentions",)

    @admin.display(description="Members")
    def member_count(self, group: MeetingGroup):
        return group.members.count()


@admin.register(GroupRole)
class GroupRoleAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = ("meeting",)
    list_display = (
        "title",
        "meeting_link",
    )
    list_filter = ("meeting__organisation",)
    search_fields = ("title", "meeting__title")
    exclude = ("mentions",)


@admin.register(GroupMembership)
class GroupMembershipAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = ()
    list_display = (
        "__str__",
        "meeting_link",
    )
    list_filter = ("meeting_group__meeting__organisation",)
    search_fields = ("title",)
    exclude = ("mentions",)

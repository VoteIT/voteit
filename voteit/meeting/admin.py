from __future__ import annotations

from contextlib import suppress

from django.contrib import messages
from typing import TYPE_CHECKING

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import models
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.template import loader
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html

from dolly.core import LiveCloner
from fsm_admin.mixins import FSMTransitionMixin

from voteit.agenda.models import AgendaItem
from voteit.meeting.dialects import dialect_registry
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
                messages.ERROR,
            )
            return
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
                messages.ERROR,
            )
            return
        meeting = queryset.first()
        with transaction.atomic(durable=True):
            cloned_meeting = clone_meeting(meeting, user=request.user)
        url = reverse(
            "admin:meeting_meeting_change", kwargs={"object_id": cloned_meeting.pk}
        )
        return HttpResponseRedirect(url)


class MeetingFilter(admin.SimpleListFilter):
    title = "Meeting"
    parameter_name = "meeting"
    search_param = "meeting"

    def lookups(self, request, model_admin):
        """
        URL query str + Human-readable
        """
        val = request.GET.get("meeting", None)
        if val:
            return ((val, "Specific meeting"),)

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        v = self.value()
        if v:
            with suppress(TypeError, ValueError):
                pk = int(v)
                return queryset.filter(**{self.search_param: pk})
            messages.add_message(request, messages.ERROR, "Not a valid meeting filter")
        return queryset


class MeetingViaAIFilter(MeetingFilter):
    search_param = "agenda_item__meeting"


class DialectFilter(admin.SimpleListFilter):
    title = "Dialect"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "dialect"
    # Constants
    VANILLA = "0"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        items = [(self.VANILLA, "None (vanilla)")]
        dialect_registry.load()
        items.extend((k, v.data.title or k) for k, v in dialect_registry.items())
        return items

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # decide how to filter the queryset.
        v = self.value()
        if v == self.VANILLA:
            return queryset.filter(installed_dialect__isnull=True)
        elif v:
            return queryset.filter(installed_dialect=v)
        return queryset


class MeetingDialectProxy(Meeting):
    class Meta:
        proxy = True


@admin.register(MeetingDialectProxy)
class MeetingDialectProxyAdmin(MeetingAdmin):
    list_display = (
        "title",
        "installed_dialect_title",
        "state",
        "start_time",
        "end_time",
    )
    list_filter = (
        "organisation",
        "state",
        DialectFilter,
    )
    search_fields = ("title", "installed_dialect")
    actions = ["uninstall_dialect", "trigger_reinstall_dialect"]
    fields = ("installed_dialect",)
    inlines = []

    @admin.display(description="Dialect")
    def installed_dialect_title(self, instance: Meeting):
        if instance.installed_dialect:
            # We don't want None here even if the dialect doesn't exist!
            return dialect_registry.get_title(
                instance.installed_dialect,
                default=f"Broken:{instance.installed_dialect}",
            )

    @admin.action(description="Uninstall dialect")
    def uninstall_dialect(self, request, queryset):
        queryset = queryset.exclude(installed_dialect__isnull=True)
        with transaction.atomic(durable=True):
            for m in queryset:
                handler = dialect_registry.get_merged_handler(m.installed_dialect)
                handler.remove(m)
        self.message_user(
            request,
            f"Uninstalled {queryset.count()}",
            messages.SUCCESS,
        )

    @admin.action(description="Trigger install dialect")
    def trigger_reinstall_dialect(self, request, queryset):
        queryset = queryset.exclude(installed_dialect__isnull=True)
        with transaction.atomic(durable=True):
            for m in queryset:
                handler = dialect_registry.get_merged_handler(m.installed_dialect)
                m.installed_dialect = None
                m.save()
                handler.install(m)
        self.message_user(
            request,
            f"Reinstalled {queryset.count()}",
            messages.SUCCESS,
        )


class MeetingAdminMixin:
    @admin.display(description="Meeting")
    def meeting_link(self, obj: MeetingContext):
        viewname = "admin:meeting_meeting_change"
        meeting_pk = getattr(obj, "meeting_id", obj.meeting.pk)
        if meeting_pk:
            try:
                link = reverse(viewname, args=[meeting_pk])
            except NoReverseMatch:
                return "%s" % meeting_pk
            return format_html(
                '<a href="{}">{}</a>',
                link,
                getattr(obj, "m_title", meeting_pk),
            )
        return "-"

    def annotate_meeting(
        self, qs: models.QuerySet, title_attr="meeting__title", pk_attr=None
    ):
        """
        Add meeting pk with same attr as other fields will have meeting relation to qs in case of no direct relation.

        """
        qs = qs.annotate(m_title=models.F(title_attr))
        if pk_attr:
            qs = qs.annotate(meeting_id=models.F(title_attr))
        return qs


@admin.register(MeetingRoles)
class MeetingRolesAdmin(MeetingAdminMixin, admin.ModelAdmin):
    autocomplete_fields = "user", "context"
    list_display = "user", "get_assigned", "meeting_link"
    list_filter = ("user__organisation",)
    search_fields = (
        "context__title",
        "user__last_name",
        "user__first_name",
        "user__userid",
    )

    def get_assigned(self, instance):
        return instance.assigned


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
        "get_roles",
    )
    list_filter = ("meeting__organisation",)
    search_fields = ("title", "meeting__title")
    exclude = ("mentions",)

    def get_roles(self, instance: GroupRole):
        return instance.roles


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

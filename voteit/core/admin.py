from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.html import format_html
from django.utils.timezone import now
from fsm_admin.mixins import FSMTransitionMixin

from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry
from voteit.core.models import User
from voteit.meeting.models import Meeting

_user_fieldsets = list(DefaultUserAdmin.fieldsets)
_user_fieldsets[0][1]["fields"] = list(_user_fieldsets[0][1]["fields"])
_user_fieldsets[0][1]["fields"].append("userid")
_user_fieldsets[0][1]["fields"].append("identity_id")
_user_fieldsets.insert(
    1,
    (
        "Organisation",
        {"fields": ("organisation",)},
    ),
)


class OnlineFilter(admin.SimpleListFilter):
    title = "Online"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "online"
    # Constants
    ONLINE = "o"
    DISCONNECTED = "d"
    WITHIN_LAST_MONTH = "l"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            (self.ONLINE, "Online"),
            (self.DISCONNECTED, "Disconnected"),
            (self.WITHIN_LAST_MONTH, "Within last 30 days"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # decide how to filter the queryset.
        if self.value():
            if self.value() == self.ONLINE:
                return queryset.filter(
                    connections__online=True,
                    connections__last_action__gt=now() - timedelta(minutes=15),
                ).distinct()
            elif self.value() == self.DISCONNECTED:
                return queryset.exclude(
                    connections__online=True,
                    connections__last_action__gt=now() - timedelta(minutes=15),
                ).distinct()
            elif self.value() == self.WITHIN_LAST_MONTH:
                return queryset.filter(
                    connections__last_action__gt=now() - timedelta(days=30)
                ).distinct()


class LinkedFilter(admin.SimpleListFilter):
    title = "ID-linked"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "linked"
    # Constants
    YES = "1"
    NO = "0"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            (self.YES, "Yes"),
            (self.NO, "No"),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # decide how to filter the queryset.
        if self.value():
            if self.value() == self.YES:
                return queryset.filter(
                    identity_id__isnull=False,
                ).distinct()
            elif self.value() == self.NO:
                return queryset.filter(
                    identity_id__isnull=True,
                ).distinct()


@admin.register(User)
class UserAdmin(FSMTransitionMixin, DefaultUserAdmin):
    fsm_field = ("state",)
    fieldsets = _user_fieldsets
    list_display = (
        "__str__",
        "organisation",
        "email",
        "first_name",
        "last_name",
        "date_joined",
        "is_linked",
    )
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "userid",
        "username",
    )
    list_filter = (
        "organisation",
        "state",
        OnlineFilter,
        LinkedFilter,
        "is_active",
        "date_joined",
        "last_login",
    )

    @admin.display(description="ID-linked", boolean=True)
    def is_linked(self, user):
        return user.identity_id is not None


# Replace existing
admin.site.unregister(LogEntry)


@admin.register(LogEntry)
class VoteITLogEntryAdmin(LogEntryAdmin):
    list_display = LogEntryAdmin.list_display + ["meeting"]
    list_filter = ["actor__organisation"] + LogEntryAdmin.list_filter

    @admin.display(description="Meeting")
    def meeting(self, obj: LogEntry):
        if meeting_pk := obj.additional_data and obj.additional_data.get("m", None):
            try:
                meeting = Meeting.objects.get(pk=meeting_pk)
            except Meeting.DoesNotExist as exc:
                return f"Deleted: {meeting_pk}"
            viewname = "admin:meeting_meeting_change"
            try:
                link = reverse(viewname, args=[meeting.pk])
            except NoReverseMatch:
                return "%s" % meeting
            return format_html('<a href="{}">{}</a>', link, meeting)
        return "-"

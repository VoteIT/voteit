from logging import getLogger

from django.contrib import admin

from voteit.invites.models import MeetingGroupAnnotation
from voteit.invites.models import MeetingInvite
from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingFilter

logger = getLogger(__name__)


class MeetingGroupAnnotationInline(admin.TabularInline):
    model = MeetingGroupAnnotation
    fields = "meeting_group", "group_role"
    autocomplete_fields = (
        "meeting_group",
        "group_role",
    )
    extra = 1


@admin.register(MeetingInvite)
class MeetingInviteAdmin(MeetingAdminMixin, admin.ModelAdmin):
    search_fields = (
        "user_data__email",
        "user_data__swedish_ssn",
        "meeting__title",
    )
    readonly_fields = ("state",)
    list_display = (
        "__str__",
        "meeting_link",
        "state",
        "used_by",
        "get_roles",
    )
    list_filter = (
        "state",
        MeetingFilter,
        "meeting__organisation",
    )
    autocomplete_fields = (
        "meeting",
        "used_by",
    )
    inlines = (MeetingGroupAnnotationInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)

    def get_roles(self, instance: MeetingInvite):
        return instance.roles

    # FIXME: Filter type

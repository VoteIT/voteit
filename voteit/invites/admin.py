from logging import getLogger

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

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
class MeetingInviteAdmin(FSMTransitionMixin, MeetingAdminMixin, admin.ModelAdmin):
    fsm_field = ("state",)
    search_fields = (
        "user_data__email",
        "user_data__swedish_ssn",
        "meeting__title",
    )
    readonly_fields = (
        "state",
        "created_by",
    )
    list_display = (
        "__str__",
        "meeting_link",
        "state",
        "used_by",
        "roles",
    )
    list_filter = (
        "state",
        MeetingFilter,
        "meeting__organisation",
    )
    autocomplete_fields = (
        "meeting",
        "used_by",
        "created_by",
    )
    inlines = (MeetingGroupAnnotationInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)

    # FIXME: Filter type

from logging import getLogger

from django.contrib import admin
from django.contrib import messages
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


# @admin.register(InviteDispatch)
# class InviteDispatchAdmin(admin.ModelAdmin):
#     list_display = (
#         "meeting",
#         "created_by",
#         "created",
#         "subject",
#         "dispatcher_name",
#     )
#     list_filter = ("meeting__organisation",)
#     actions = ["send_all_invites"]
#
#     @admin.action(description="Send invites")
#     def send_all_invites(self, request, queryset):
#         if queryset.count() == 1:
#             invite_dispatch: InviteDispatch = queryset.first()
#             logger.info(
#                 "Sending %s for meeting %s",
#                 invite_dispatch.subject,
#                 invite_dispatch.meeting.title,
#             )
#             sent, failed, skipped = invite_dispatch.send_scheduled()
#             if failed:
#                 self.message_user(
#                     request,
#                     f"{failed} failed, {sent} sent and {skipped} skipped",
#                     messages.WARNING,
#                 )
#             elif sent:
#                 self.message_user(
#                     request,
#                     f"All {sent} sent successfully, {skipped} was skipped",
#                     messages.SUCCESS,
#                 )
#             else:
#                 if skipped:
#                     self.message_user(
#                         request, f"Nothing done, {skipped} skipped", messages.WARNING
#                     )
#                 else:
#                     self.message_user(request, "Nothing done", messages.WARNING)
#
#         else:
#             self.message_user(request, "You must select exactly one", messages.ERROR)

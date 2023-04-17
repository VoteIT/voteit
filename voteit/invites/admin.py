from logging import getLogger

from django.contrib import admin
from django.contrib import messages
from fsm_admin.mixins import FSMTransitionMixin

from voteit.invites.models import MeetingInvite


logger = getLogger(__name__)


@admin.register(MeetingInvite)
class MeetingInviteAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = [
        "state",
    ]
    readonly_fields = ("state",)
    list_display = (
        "meeting",
        "state",
        "used_by",
        "roles",
    )
    list_filter = (
        "meeting__organisation",
        "state",
    )
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

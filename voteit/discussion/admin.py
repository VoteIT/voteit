from django.contrib import admin

from voteit.agenda.admin import AgendaItemAdminMixin
from voteit.discussion.models import DiscussionPost
from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingViaAIFilter


@admin.register(DiscussionPost)
class DiscussionPostAdmin(MeetingAdminMixin, AgendaItemAdminMixin, admin.ModelAdmin):
    list_filter = (
        MeetingViaAIFilter,
        "author__organisation",
    )
    list_display = (
        "__str__",
        "meeting_link",
        "agenda_item_link",
        "author",
        "meeting_group",
    )
    autocomplete_fields = (
        "agenda_item",
        "author",
        "meeting_group",
        "mentions",
    )
    search_fields = (
        "body",
        "agenda_item__title",
        "agenda_item__meeting__title",
        "author__first_name",
        "author__last_name",
        "author__userid",
        "meeting_group__groupid",
        "meeting_group__title",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = self.annotate_ai(qs)
        qs = qs.prefetch_related("author")
        return self.annotate_meeting(
            qs,
            title_attr="agenda_item__meeting__title",
            pk_attr="agenda_item__meeting_id",
        )

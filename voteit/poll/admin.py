from django.contrib import admin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingFilter
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll


@admin.register(ElectoralRegister)
class ERAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = "__str__", "meeting_link", "voters_count"
    list_filter = (
        MeetingFilter,
        "meeting__organisation",
    )
    autocomplete_fields = ("meeting",)

    @admin.display(description="Voters")
    def voters_count(self, er: ElectoralRegister) -> int:
        return len(er.voter_data)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)


@admin.register(Poll)
class PollAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "meeting_link",
        "state",
        "method_name",
        "electoral_register",
        "vote_count",
    )
    list_filter = (
        MeetingFilter,
        "state",
        "method_name",
        "meeting__organisation",
    )
    search_fields = (
        "title",
        "body",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = ("agenda_item", "meeting", "mentions", "proposals")
    exclude = ("state",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)

    @admin.display(description="Votes")
    def vote_count(self, poll: Poll):
        return poll.votes.count()

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import VoterWeight


class VoterWeightItemInline(admin.TabularInline):
    model = VoterWeight
    fields = "user", "weight"
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(ElectoralRegister)
class ERAdmin(admin.ModelAdmin):
    list_display = "__str__", "meeting", "voters_count"
    list_filter = ("meeting__organisation", "meeting")
    autocomplete_fields = ("meeting",)

    def voters_count(self, er: ElectoralRegister) -> int:
        return er.voters.count()

    voters_count.short_description = "Voters"

    inlines = (VoterWeightItemInline,)


@admin.register(VoterWeight)
class VoterWeightAdmin(admin.ModelAdmin):
    list_display = "__str__", "meeting_title", "user", "weight"
    list_filter = ("register__meeting__organisation", "register__meeting", "user")
    search_fields = (
        "register__meeting__title",
        "user__userid",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("user",)

    def meeting_title(self, obj: VoterWeight):
        return obj.register.meeting.title

    meeting_title.short_description = "Meeting"


@admin.register(Poll)
class PollAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = (
        "title",
        "state",
        "method_name",
        "electoral_register",
        "vote_count",
    )
    list_filter = (
        "state",
        "agenda_item",
        "method_name",
    )
    search_fields = (
        "title",
        "body",
        "agenda_item__title",
        "agenda_item__meeting__title",
    )
    autocomplete_fields = ("agenda_item", "meeting", "mentions", "proposals")
    exclude = ("state",)

    def vote_count(self, poll: Poll):
        return poll.votes.count()

    vote_count.short_description = "Votes"

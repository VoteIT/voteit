from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.meeting.admin import MeetingAdminMixin
from voteit.meeting.admin import MeetingFilter
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import VoterWeight


class VoterWeightItemInline(admin.TabularInline):
    model = VoterWeight
    fields = "user", "weight"
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(ElectoralRegister)
class ERAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = "__str__", "meeting_link", "voters_count"
    list_filter = (
        MeetingFilter,
        "meeting__organisation",
    )
    autocomplete_fields = ("meeting",)
    inlines = (VoterWeightItemInline,)

    @admin.display(description="Voters")
    def voters_count(self, er: ElectoralRegister) -> int:
        return er.voters.count()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.annotate_meeting(qs)


class MeetingViaRegFilter(MeetingFilter):
    search_param = "register__meeting"


@admin.register(VoterWeight)
class VoterWeightAdmin(MeetingAdminMixin, admin.ModelAdmin):
    list_display = "__str__", "meeting_link", "user", "weight"
    list_filter = (
        MeetingViaRegFilter,
        "register__meeting__organisation",
    )
    search_fields = (
        "register__meeting__title",
        "user__userid",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related("register", "user")
        return self.annotate_meeting(
            qs, title_attr="register__meeting__title", pk_attr="register__meeting_id"
        )


@admin.register(Poll)
class PollAdmin(MeetingAdminMixin, FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
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

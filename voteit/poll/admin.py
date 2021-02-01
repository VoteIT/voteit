from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin
from django.utils.translation import gettext_lazy as _

from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll


@admin.register(ElectoralRegister)
class ERAdmin(admin.ModelAdmin):
    pass


@admin.register(Poll)
class PollAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = "title", "state", "method_name", "electoral_register", "vote_count"
    list_filter = "state", "agenda_item", "method_name"
    search_fields = "title", "body", "agenda_item__title", "agenda_item__meeting__title"
    exclude = ("state",)

    def vote_count(self, poll: Poll):
        return poll.votes.count()

    vote_count.short_description = _("Votes")

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll


@admin.register(ElectoralRegister)
class ERAdmin(admin.ModelAdmin):
    pass


@admin.register(Poll)
class PollAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]

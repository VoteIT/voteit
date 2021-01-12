from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.presence.models import PresenceSystem
from voteit.presence.models import PresenceCheck
from voteit.presence.models import Presence


@admin.register(PresenceSystem)
class PresenceSystemAdmin(admin.ModelAdmin):
    list_display = ("meeting",)
    search_fields = ("meeting__title",)


@admin.register(PresenceCheck)
class PresenceCheckAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    list_display = "state", "presence_system", "opened", "closed"
    list_filter = ("state",)
    exclude = "state",


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = "user", "presence_check", "created"


from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin
from voteit.access_policy.app.policies import ModeratorApprovedAccess, AutomaticAccess
from voteit.access_policy.app.policies.moderator_approved import AccessRequest
from voteit.access_policy.models import MeetingInvite


@admin.register(AutomaticAccess)
class AutomaticAccessAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "active",
        "roles_given",
    )
    list_filter = (
        "meeting",
        "active",
    )
    autocomplete_fields = ("meeting",)


@admin.register(ModeratorApprovedAccess)
class ModeratorApprovedAccessAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "active",
    )
    list_filter = (
        "meeting",
        "active",
    )
    autocomplete_fields = ("meeting",)


@admin.register(AccessRequest)
class AccessRequestAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    readonly_fields = ("state",)


@admin.register(MeetingInvite)
class MeetingInviteAdmin(FSMTransitionMixin, admin.ModelAdmin):
    fsm_field = ["state"]
    readonly_fields = ("state",)

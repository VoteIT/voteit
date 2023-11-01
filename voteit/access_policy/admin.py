from logging import getLogger

from django.contrib import admin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.access_policy.app.policies import AutomaticAccess


logger = getLogger(__name__)


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


# @admin.register(ModeratorApprovedAccess)
# class ModeratorApprovedAccessAdmin(admin.ModelAdmin):
#     list_display = (
#         "meeting",
#         "active",
#     )
#     list_filter = (
#         "meeting",
#         "active",
#     )
#     autocomplete_fields = ("meeting",)
#
#
# @admin.register(AccessRequest)
# class AccessRequestAdmin(FSMTransitionMixin, admin.ModelAdmin):
#     fsm_field = ["state"]
#     readonly_fields = ("state",)

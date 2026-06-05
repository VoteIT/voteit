from logging import getLogger

from django.contrib import admin

from voteit.access_policy.app.policies import AutomaticAccess


logger = getLogger(__name__)


@admin.register(AutomaticAccess)
class AutomaticAccessAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "active",
        "get_roles_given",
    )
    list_filter = (
        "meeting__organisation",
        "active",
    )
    autocomplete_fields = ("meeting",)

    def get_roles_given(self, instance: AutomaticAccess):
        return instance.roles_given

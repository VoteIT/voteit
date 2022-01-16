from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from fsm_admin.mixins import FSMTransitionMixin

from voteit.core.models import User


_user_fieldsets = list(DefaultUserAdmin.fieldsets)
_user_fieldsets[0][1]["fields"] = list(_user_fieldsets[0][1]["fields"])
_user_fieldsets[0][1]["fields"].append("userid")
_user_fieldsets.insert(
    1,
    (
        "Organisation",
        {"fields": ("organisation",)},
    ),
)


@admin.register(User)
class UserAdmin(FSMTransitionMixin, DefaultUserAdmin):
    fsm_field = ("state",)
    fieldsets = _user_fieldsets
    list_display = ("__str__", "organisation", "email", "first_name", "last_name", "date_joined")
    search_fields = ("first_name", "last_name", "email", "userid")
    list_filter = ("organisation", "state", "is_active", "date_joined")

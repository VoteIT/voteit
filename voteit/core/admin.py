from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.utils.translation import gettext_lazy as _
from fsm_admin.mixins import FSMTransitionMixin

from voteit.core.models import User


_user_fieldsets = list(DefaultUserAdmin.fieldsets)
_user_fieldsets[0][1]["fields"] = list(_user_fieldsets[0][1]["fields"])
_user_fieldsets[0][1]["fields"].append("userid")
_user_fieldsets.insert(
    1,
    (
        _("Organisation"),
        {"fields": ("organisation",)},
    ),
)


@admin.register(User)
class UserAdmin(FSMTransitionMixin, DefaultUserAdmin):
    fsm_field = ["state"]
    fieldsets = _user_fieldsets

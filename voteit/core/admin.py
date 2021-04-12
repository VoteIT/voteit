from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.utils.translation import gettext_lazy as _

from voteit.core.models import User


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    fieldsets = list(DefaultUserAdmin.fieldsets)
    fieldsets.insert(
        1,
        (
            _("Organisation"),
            {"fields": ("organisation",)},
        ),
    )

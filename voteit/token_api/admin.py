from django.contrib import admin
from rest_framework_api_key.admin import APIKeyModelAdmin

from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user


@admin.register(MeetingAPIKey)
class MeetingAPIKeyAdmin(APIKeyModelAdmin):
    model = MeetingAPIKey

    list_display = APIKeyModelAdmin.list_display + ("meeting", "last_used")
    list_filter = APIKeyModelAdmin.list_filter + ("revoked", "expiry_date", "last_used")
    search_fields = APIKeyModelAdmin.search_fields + ("meeting__title",)
    readonly_fields = ("last_used",)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None:
            fields = fields + ("meeting", "user")
        return fields

    def get_exclude(self, request, obj=None):
        excluded = list(super().get_exclude(request, obj) or [])
        if obj is None:
            excluded.append("user")
        return excluded

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.user = create_api_key_user(obj.meeting)
        super().save_model(request, obj, form, change)

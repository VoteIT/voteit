from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from voteit.messaging.models import Connection
#from voteit.messaging.models import Subscription


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = "user", "online", "channel_name", "first_seen", "last_action"
    list_filter = "online", "user", "first_seen", "last_action"
    readonly_fields = "online", "first_seen", "last_action"
    search_fields = ("user",)


# @admin.register(Subscription)
# class SubscriptionAdmin(admin.ModelAdmin):
#     list_display = "connection", "obj_pk", "channel_type"
#     list_filter = "obj_pk", "channel_type"
#     search_fields = ("connection",)

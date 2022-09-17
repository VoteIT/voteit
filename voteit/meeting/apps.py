from django.apps import AppConfig


class MeetingConfig(AppConfig):
    name = "voteit.meeting"
    verbose_name = "Meeting"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.meeting import roles
        from voteit.meeting import rules
        from voteit.meeting.rest_api import views
        from voteit.meeting import channels
        from voteit.meeting import messages
        from voteit.meeting import signals

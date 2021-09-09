from django.apps import AppConfig


class MeetingConfig(AppConfig):
    name = "voteit.meeting"
    verbose_name = "Meeting"

    def ready(self):
        from voteit.meeting import roles
        from voteit.meeting import rules
        from voteit.meeting import rest_api
        from voteit.meeting import channels
        from voteit.meeting import messages
        from voteit.meeting import signals

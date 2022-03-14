from django.apps import AppConfig


class BugReportsConfig(AppConfig):
    name = "voteit.bug_reports"
    verbose_name = "Bug reports"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from .rest_api import views

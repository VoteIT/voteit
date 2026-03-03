from django.apps import AppConfig


class NotesConfig(AppConfig):
    name = "voteit.notes"
    verbose_name = "Notes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.notes import components  # noqa
        from voteit.notes import messages  # noqa
        from voteit.notes import signals  # noqa
        from voteit.notes.rest_api import views  # noqa

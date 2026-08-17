from django.apps import AppConfig


class SFSConfig(AppConfig):
    name = "voteit.app.sfs"
    verbose_name = "SFS"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.app.sfs.rest_api import views  # noqa

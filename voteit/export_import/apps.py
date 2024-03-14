from django.apps import AppConfig


class ExportImportConfig(AppConfig):
    name = "voteit.export_import"
    verbose_name = "Export/Import"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .rest_api import register

        register()

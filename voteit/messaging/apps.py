from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "voteit.messaging"
    # An earlier, unrelated "voteit.messaging" app existed in 2021 (removed in
    # 4275017). Long-lived databases still carry its messaging.0001_initial
    # record and a stale messaging_connection table with a different schema, so
    # reusing the default "messaging" label would make Django skip our initial
    # migration as already applied. Use a distinct label instead.
    label = "voteit_messaging"
    verbose_name = "Messaging"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.contrib.auth import get_user_model
        from django.utils.module_loading import autodiscover_modules

        from voteit.messaging.channels import UserChannel

        UserChannel.model = get_user_model()
        # The consumer reads the outgoing registry when its class is created,
        # so every app's messages.py and channels.py must have been imported.
        autodiscover_modules("messages", "channels")

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

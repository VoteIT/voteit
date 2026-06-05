import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = "voteit.core"
    verbose_name = "VoteIT Core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.core.registries import content_types
        from voteit.core import models_to_register
        from voteit.core.rest_api import views  # noqa
        from voteit.core import jobs  # noqa

        while models_to_register:
            model = models_to_register.pop()
            if not model._meta.proxy:
                register_model(model, content_types)

        # Register messages
        from voteit.core.messages import register

        register()

        from voteit.core.signals import post_init_registrations

        post_init_registrations()

        try:
            import magic

            magic.from_buffer(b"\xff\xd8", mime=True)
        except Exception:
            logger.exception(
                "libmagic C library is missing or broken — image upload validation will "
                "return HTTP 400. Install it with: apt-get install libmagic1"
            )


def register_model(model, registry):
    """
    Models should be here after class_prepared is called
    >>> from voteit.core.registries import content_types
    >>> "meeting" in content_types
    True

    Registering the same model twice should raise errors
    >>> from voteit.meeting.models import Meeting
    >>> register_model(Meeting, content_types)
    Traceback (most recent call last):
    ...
    ValueError: ...

    """
    if hasattr(model, "name"):
        # Only care about models with name
        if model.name is None:
            model.name = model.__name__.lower()
        if model.name in registry:
            raise ValueError(
                f"{model.name} is already present in content registry. \n"
                f"Existing: {registry[model.name]}\n"
                f"Tried to register {model}"
            )
        registry[model.name] = model

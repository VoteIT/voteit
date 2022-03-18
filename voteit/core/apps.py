from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "voteit.core"
    verbose_name = "VoteIT Core"

    def ready(self):
        from voteit.core.registries import content_types
        from voteit.core.registries import permissions
        from voteit.core import models_to_register
        from voteit.core.utils import prepare_available_transitions

        while models_to_register:
            model = models_to_register.pop()
            register_model(model, content_types)

        # Make sure linked permissions make sense
        permissions.validate_registry()

        # Cache all workflow transitions
        prepare_available_transitions()

        # Register messages
        from voteit.core.messages import register

        register()


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

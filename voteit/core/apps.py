from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    name = "voteit.core"
    verbose_name = _("VoteIT Core")

    def ready(self):
        from voteit.core.registries import content_types
        from voteit.core.registries import permissions
        from voteit.core import models_to_register
        from voteit.core.utils import prepare_available_transitions

        for model in models_to_register:
            register_model(model, content_types)
        del models_to_register

        # Make sure linked permissions make sense
        permissions.validate_registry()

        # Cache all workflow transitions
        prepare_available_transitions()


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

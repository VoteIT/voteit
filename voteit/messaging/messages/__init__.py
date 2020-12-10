
def register():
    """ Just make sure all code is imported and registered. """
    from . import channels, user, progress, schema, roles, text
    from django.conf import settings

    if settings.DEBUG:
        from . import testing

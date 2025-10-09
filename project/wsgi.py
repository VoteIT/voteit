"""
WSGI config for voteit project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# FIXME: Remove this?
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings_production")

application = get_wsgi_application()

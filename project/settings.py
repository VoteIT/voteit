"""
Test settings
"""
import os
from voteit.settings_tpl import *

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "change-me"
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
ALLOWED_HOSTS = ["*"]

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

ID_HOST = "http://example.com"  # Required setting by organisation app

ROOT_URLCONF = "project.urls"


WSGI_APPLICATION = "voteit_project.wsgi.application"
ASGI_APPLICATION = "voteit_project.routing.application"
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    }
}

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Stockholm"
USE_I18N = True
USE_L10N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rq_console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
        # "json": {
        #     # Must be () otherwise timestamp won't be passed along!
        #     "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        #     "format": "%(message)s",
        #     "datefmt": "%H:%M:%S",
        #     "timestamp": True,
        # },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "rq_console",
        },
        "rq_console": {
            "level": "DEBUG",
            "class": "rq.logutils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
        # "json": {
        #     "level": "DEBUG",
        #     "class": "logging.StreamHandler",
        #     "formatter": "json",
        # },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "voteit": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "envelope": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "envelope.consumers.websocket.event": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rq.worker": {
            "handlers": [
                "rq_console",
            ],
            "level": "INFO",
            "propagate": False,
        },
        # "rules": {
        #     "handlers": ["console"],
        #     "level": "DEBUG",
        #     "propagate": False,
        # },
    },
}

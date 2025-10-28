import os
import sys
from importlib.util import find_spec
from pathlib import Path

from voteit.settings_tpl import *

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent
MEETING_DIALECTS_DIR = os.path.join(BASE_DIR, "dialects")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in ("true", "1")

STATIC_ROOT = "/app/static/"
ALLOWED_HOSTS = ["127.0.0.1"] + os.getenv("HOST", "").split()
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://\w+\.voteit\.se$",
    r"^https://\w+\.betahaus\.net$",
]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    from hashlib import md5

    SECRET_KEY = md5().hexdigest()

_marker = object()
for env_setting in (
    "EXPORT_SECRET_KEY",
    "ID_HOST",
    "ID_HOST_BACKEND",
    "ID_PROXY_API_KEY",
    "EMAIL_HOST",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
    "EMAIL_TIMEOUT",
    "EMAIL_SSL_KEYFILE",
    "EMAIL_SSL_CERTFILE",
    "AUDITLOG_TWO_STEP_MIGRATION",
    "AUDITLOG_USE_TEXT_CHANGES_IF_JSON_IS_NOT_PRESENT",
):
    val = os.getenv(env_setting, _marker)
    if val is not _marker:
        setattr(sys.modules[__name__], env_setting, val)

# Application definition
INSTALLED_APPS += os.getenv("DJANGO_INSTALLED_APPS", "").split()


# Enable tools if there's a mounted volume with that name
if find_spec("voteit_tools"):
    INSTALLED_APPS.append("voteit_tools")

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.routing.application"


# RQ
RQ_QUEUES["default"]["HOST"] = "redis_rq"
RQ_QUEUES["long"]["HOST"] = "redis_rq"
RQ_QUEUES[ENVELOPE_CONNECTIONS_QUEUE]["DB"] = 2
RQ_QUEUES[ENVELOPE_CONNECTIONS_QUEUE]["HOST"] = "redis_rq"
RQ_QUEUES[ENVELOPE_TIMESTAMP_QUEUE]["DB"] = 3
RQ_QUEUES[ENVELOPE_TIMESTAMP_QUEUE]["HOST"] = "redis_rq"

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("redis", 6379)],
            "capacity": 1500,  # default 100
            "expiry": 60,  # default 60
            "group_expiry": 86400,  # default 86400
        },
    },
}


# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres",
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
    }
}

# Cache
if MEMCACHE_LOCATION := os.getenv("MEMCACHE_LOCATION"):
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
            "LOCATION": MEMCACHE_LOCATION,
        }
    }


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Stockholm"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")
MEETING_DIALECTS_DIR = os.path.join(BASE_DIR, "dialects")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rq_console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
        "json": {
            # Must be () otherwise timestamp won't be passed along!
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(message)s",
            "datefmt": "%H:%M:%S",
            "timestamp": True,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "rq_console": {
            "level": "DEBUG",
            "class": "rq.logutils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
        "json": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "voteit": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "envelope": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "envelope.consumers.websocket.event": {
            "handlers": ["json"],
            "level": "DEBUG",
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

if SLACK_WEBHOOK_URL := os.getenv("SLACK_LOGGER_WEBHOOK"):
    LOGGING["formatters"]["slack"] = {
        "()": "slack_logger.SlackFormatter",
    }
    LOGGING["handlers"]["slack"] = {
        "()": "slack_logger.SlackHandler",
        "level": "DEBUG",
        "formatter": "slack",
        "username": "logger",
        "icon_emoji": ":robot_face:",
        "url": SLACK_WEBHOOK_URL,
    }
    LOGGING["loggers"]["voteit.notification"] = {
        "handlers": ["slack"],
        "level": "INFO",
        "propagate": False,
    }


# Set SENTRY_DSN env variable to enable sentry logging.
if SENTRY_DSN := os.getenv("SENTRY_DSN"):  # pragma: no cover
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.scrubber import EventScrubber, DEFAULT_PII_DENYLIST

    SENTRY_TRACES_SAMPLERATE = float(os.getenv("SENTRY_TRACES_SAMPLERATE", 1.0))
    SENTRY_PROFILES_SAMPLERATE = float(os.getenv("SENTRY_PROFILES_SAMPLERATE", 1.0))
    # Remember trailing slash!
    SENTRY_IGNORE_PATHS = os.getenv("SENTRY_IGNORE_PATHS", "/api/health/").split(",")
    SENTRY_PII = os.getenv("SENTRY_PII", "false").lower() == "true"
    SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "local_dev")
    SENTRY_RELEASE = os.getenv("BACKEND_VERSION", "local_dev")

    def traces_sampler(sampling_context: dict):
        if (
            sampling_context.get("wsgi_environ", {}).get("PATH_INFO")
            in SENTRY_IGNORE_PATHS
        ):
            return 0
        return SENTRY_TRACES_SAMPLERATE

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=SENTRY_TRACES_SAMPLERATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLERATE,
        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
        send_default_pii=SENTRY_PII,
        # Should report only user primary key, no other user info
        event_scrubber=EventScrubber(
            pii_denylist=[*DEFAULT_PII_DENYLIST, "email", "username"]
        ),
        # Filter out specific endpoints to avoid spamming
        traces_sampler=traces_sampler,
        # Env tag
        environment=SENTRY_ENVIRONMENT,
        # Release tag
        release=SENTRY_RELEASE,
    )

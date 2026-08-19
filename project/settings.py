import os
import sys
from importlib.util import find_spec
from pathlib import Path

from voteit.settings_tpl import *

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in ("true", "1")
VERBOSE_PERMISSIONS = DEBUG
LOCALE_PATHS = [os.path.join(BASE_DIR, "locales")]
MEDIA_URL = "media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

STATIC_ROOT = "/app/static/"
ALLOWED_HOSTS = ["127.0.0.1"] + os.getenv("HOST", "").split()
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://\w+\.voteit\.se$",
    r"^https://\w+\.betahaus\.net$",
]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY not set")

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
ASGI_APPLICATION = "project.asgi.application"


# Auth & "social" auth
SITE_ID = 1
SOCIAL_AUTH_JSONFIELD_ENABLED = True
SOCIAL_AUTH_FIELDS_STORED_IN_SESSION = ["next"]
SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL = False
# Load all SOCIAL_AUTH__
for env_k, env_v in os.environ.items():
    if env_k.startswith("SOCIAL_AUTH_"):
        if env_k.endswith("_SCOPE"):
            env_v = env_v.split()
        setattr(sys.modules[__name__], env_k, env_v)

SOCIAL_AUTH_PIPELINE = [
    "voteit.organisation.pipeline.org_active",
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    # "social_core.pipeline.social_auth.auth_allowed",
    # "social_core.pipeline.social_auth.social_user",
    "voteit.organisation.pipeline.social_user",
    "social_core.pipeline.user.get_username",
    "voteit.organisation.pipeline.create_user",
    "voteit.organisation.pipeline.ensure_userid",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "voteit.organisation.pipeline.inherit_users",
    "voteit.organisation.pipeline.bump_permissions",
    "voteit.organisation.pipeline.remove_nonmatching_email",
]


AUTHENTICATION_BACKENDS = [
    "voteit.organisation.backends.IDProxyOAuth2",
] + AUTHENTICATION_BACKENDS
LOGIN_REDIRECT_URL = "/"
LOGIN_ERROR_URL = "/error"

# RQ
REDIS_RQ_HOST = os.getenv("REDIS_RQ_HOST", "redis_rq")
RQ_QUEUES["default"]["HOST"] = REDIS_RQ_HOST
RQ_QUEUES["long"]["HOST"] = REDIS_RQ_HOST

# Channels
REDIS_CHANNEL_HOST = os.getenv("REDIS_CHANNEL_HOST", "redis")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_CHANNEL_HOST, 6379)],
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
        "OPTIONS": {
            "pool": True,
        },
    }
}

# Cache
if REDIS_CACHE_LOCATION := os.getenv("REDIS_CACHE_LOCATION"):
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_LOCATION,  # "redis://127.0.0.1:6379"
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
        "chanx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "voteit.messaging": {
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

    SENTRY_TRACES_SAMPLERATE = float(os.getenv("SENTRY_TRACES_SAMPLERATE", 1.0))
    SENTRY_PROFILES_SAMPLERATE = float(os.getenv("SENTRY_PROFILES_SAMPLERATE", 1.0))
    # Remember trailing slash!
    SENTRY_IGNORE_PATHS = os.getenv("SENTRY_IGNORE_PATHS", "/api/health/").split(",")
    SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "local_dev")
    SENTRY_RELEASE = os.getenv("BACKEND_VERSION", "local_dev")

    def traces_sampler(sampling_context: dict):
        if (
            sampling_context.get("wsgi_environ", {}).get("PATH_INFO")
            in SENTRY_IGNORE_PATHS
        ):
            return 0
        return SENTRY_TRACES_SAMPLERATE

    def before_send(event, hint):
        if user := event.get("user"):
            event["user"] = {"id": user.get("id")}
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=SENTRY_TRACES_SAMPLERATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLERATE,
        # This must be on to fetch users
        send_default_pii=True,
        # Scrub this way instead
        before_send=before_send,
        # Filter out specific endpoints to avoid spamming
        traces_sampler=traces_sampler,
        # Env tag
        environment=SENTRY_ENVIRONMENT,
        # Release tag
        release=SENTRY_RELEASE,
    )

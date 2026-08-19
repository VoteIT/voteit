import os

# Base required settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
AUTH_USER_MODEL = "core.User"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Installed apps
INSTALLED_APPS = [
    "daphne",
    "voteit.stats",  # Before admin, to override templates
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rules",
    "rest_framework",
    "rest_framework_api_key",
    "django_filters",
    "channels",
    "chanx.channels",
    "corsheaders",
    "auditlog",
    "django_rq",
    "social_django",
    "controlcenter",
    "voteit.core",
    "voteit.messaging",
    "voteit.meeting",
    "voteit.export_import",
    "voteit.active",
    "voteit.access_policy",
    "voteit.agenda",
    "voteit.components",
    "voteit.notes",
    "voteit.presence",
    "voteit.invites",
    "voteit.proposal",
    "voteit.discussion",
    "voteit.poll",
    "voteit.speaker",
    "voteit.organisation",
    "voteit.participant_number",
    "voteit.reactions",
    "voteit.room",
    "voteit.participant_tags",
    "voteit.token_api",
    "voteit.app.sfs",
    "voteit.app.skk",
    "voteit.app.skr",
]

CONTROLCENTER_DASHBOARDS = (
    ("now", "voteit.stats.dashboards.NowStats"),
    ("latest", "voteit.stats.dashboards.LatestStats"),
)
CONTROLCENTER_CHARTIST_COLORS = "material"  # Easier to tell apart

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Auth backends
AUTHENTICATION_BACKENDS = [
    "rules.permissions.ObjectPermissionBackend",
    "voteit.core.backends.PrefetchedModelBackend",
]

# Channels / chanx / RQ
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            # "hosts": ["redis://:127.0.0.1:6379/0"], <- Doesn't work
            "hosts": [("redis", 6379)],
        },
    },
}
CHANX = {
    "MESSAGE_ACTION_KEY": "action",
    # Suppress the complete/group_complete acks; the frontend does not use
    # them. Tests turn this on via voteit.messaging.testing.ws_test_settings.
    "SEND_COMPLETION": False,
    "SEND_MESSAGE_IMMEDIATELY": True,
    # We authenticate off scope["user"], not DRF, so there is no auth message.
    "SEND_AUTHENTICATION_MESSAGE": False,
    # VoteIT speaks snake_case on the wire.
    "CAMELIZE": False,
    "LOG_WEBSOCKET_MESSAGE": True,
    "LOG_IGNORED_ACTIONS": ["s.ping", "s.pong"],
    "ASYNCAPI_TITLE": "VoteIT WebSocket API",
}

# Seconds between Connection.last_action writes for a busy socket.
VOTEIT_CONNECTION_UPDATE_INTERVAL = 60
# Collapse this many or more same-action messages to one target into a
# single <action>.batch message when a transaction commits.
VOTEIT_BATCH_THRESHOLD = 3

RQ_QUEUES = {
    "default": {
        "HOST": "redis",
        "PORT": 6379,
        "DB": 1,
    },
    "long": {
        "HOST": "redis",
        "PORT": 6379,
        "DB": 1,
        "DEFAULT_TIMEOUT": 600,
        "DEFAULT_RESULT_TTL": 3600 * 24 * 7,
    },
}

# How long (seconds) to coalesce bursts of votes on the same poll before
# broadcasting an updated PollStatus - see voteit.poll.jobs.
POLL_STATUS_THROTTLE_SECONDS = float(os.getenv("POLL_STATUS_THROTTLE_SECONDS", 1.5))

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "voteit.core.rest_api.filters.ActionAnnotatedDjangoFilterBackend"
    ],
    "DEFAULT_THROTTLE_RATES": {
        "token_api_user": "60/min",
        "token_api_anon": "1/sec",
    },
}
# Auditlog
AUDITLOG_DISABLE_ON_RAW_SAVE = True

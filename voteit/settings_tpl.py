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
    "django_filters",
    "django_fsm",
    "fsm_admin",
    "channels",
    "envelope.app.online_channel",
    "envelope.app.user_channel",
    "envelope",
    "corsheaders",
    "auditlog",
    "django_rq",
    "social_django",
    "voteit.core",
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
    "controlcenter",
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
    "django.contrib.auth.backends.ModelBackend",
]

# Channels / Envelope / RQ
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            # "hosts": ["redis://:127.0.0.1:6379/0"], <- Doesn't work
            "hosts": [("redis", 6379)],
        },
    },
}
# Must exist within RQ config
ENVELOPE_CONNECTIONS_QUEUE = "conn"
ENVELOPE_TIMESTAMP_QUEUE = "ts"

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
    ENVELOPE_CONNECTIONS_QUEUE: {
        "HOST": "redis",
        "PORT": 6379,
        "DB": 1,
    },
    ENVELOPE_TIMESTAMP_QUEUE: {
        "HOST": "redis",
        "PORT": 6379,
        "DB": 1,
    },
}

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
}
# Auditlog
AUDITLOG_DISABLE_ON_RAW_SAVE = True

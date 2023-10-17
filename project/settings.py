"""
Test settings
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "change-me"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
ALLOWED_HOSTS = ["*"]

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

ID_HOST = "http://example.com"  # Required setting by organisation app

# Must exist within RQ config
ENVELOPE_CONNECTIONS_QUEUE = "conn"
ENVELOPE_TIMESTAMP_QUEUE = "ts"
# Application definition

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dolly",
    "rules",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "django_fsm",
    "fsm_admin",
    "channels",
    "envelope",
    "envelope.app.user_channel",
    "corsheaders",
    "auditlog",
    "django_rq",
    # VoteIT parts
    "voteit.core",
    "voteit.meeting",
    "voteit.active",
    "voteit.access_policy",
    "voteit.agenda",
    "voteit.bug_reports",
    "voteit.components",
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
]
AUTH_USER_MODEL = "core.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"

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
AUTHENTICATION_BACKENDS = (
    "voteit.core.permissions.VerbosePermissionBackend",
    "django.contrib.auth.backends.ModelBackend",
)
CHECK_PERMISSION_CONTEXT = True


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

# MEETING_DIALECTS_DIR = os.path.join(BASE_DIR, "../../member_dialects/dialects")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

RQ_QUEUES = {
    "default": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 1,
    },
    "conn": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 1,
    },
    "ts": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 1,
    },
}

AUDITLOG_DISABLE_ON_RAW_SAVE = True
_BC_EXCL = ["modified", "created"]
_BC_INCL = ["body", "mentions", "tags", "title", "author", "last_modified_by"]
AUDITLOG_INCLUDE_TRACKING_MODELS = (
    "access_policy.automaticaccess",
    {
        "model": "agenda.agendaitem",
        "include_fields": ["state", "block_discussion", "block_proposals"] + _BC_INCL,
    },
    {
        "model": "active.activeuser",
        "include_fields": ["meeting", "user"],
    },
    "components.meetingcomponent",
    "components.organisationcomponent",
    {
        "model": "core.user",
        "include_fields": [
            "state",
            "organisation",
            "userid",
            "username",
            "identity_id",
            "first_name",
            "last_name",
            "email",
            "last_login",
            "is_staff",
            "is_active",
            "is_superuser",
        ],
    },
    {
        "model": "discussion.discussionpost",
        "exclude_fields": ["reaction_set"] + _BC_EXCL,
    },
    {
        "model": "invites.meetinginvite",
        "exclude_fields": ["send_state", "last_sent", "used_at"] + _BC_EXCL,
    },
    "meeting.meetingroles",
    {
        "model": "meeting.meeting",
        "include_fields": [
            "organisation",
            "state",
            "public",
            "visible_in_lists",
            "er_policy_name",
            "proposal_id_policy_name",
            "installed_dialect",
        ]
        + _BC_INCL,
    },
    {
        "model": "meeting.meetinggroup",
        "include_fields": [
            "groupid",
            "title",
            "meeting",
            "votes",
            "body",
        ],
        "m2m_fields": {"members"},
    },
    {
        "model": "meeting.groupmembership",
        "include_fields": ["user", "meeting_group", "role", "votes"],
    },
    {
        "model": "meeting.grouprole",
        "include_fields": [
            "title",
            "role_id",
            "meeting",
            "can_propose_as",
            "can_discuss_as",
            "roles",
        ],
    },
    "organisation.organisationroles",
    {
        "model": "organisation.organisation",
        "include_fields": ["host", "page_title", "body", "title"],
    },
    "participant_number.pnsystem",
    {
        "model": "poll.poll",
        "exclude_fields": [
            "started",
            "closed",
            "ballot_data",
            "ballot_checksum",
            "abstains",
            "result_data",
            "votes",
        ]
        + _BC_EXCL,
    },
    {
        "model": "proposal.proposal",
        "include_fields": ["state", "meeting_group", "prop_id", "agenda_item"]
        + _BC_INCL,
    },
    {
        "model": "presence.presencecheck",
        "include_fields": ["state", "meeting"],
    },
    {
        "model": "proposal.diffproposal",
        "include_fields": [
            "state",
            "meeting_group",
            "prop_id",
            "agenda_item",
            "paragraph",
        ]
        + _BC_INCL,
    },
    {
        "model": "proposal.textdocument",
        "exclude_fields": _BC_EXCL + ["text_paragraphs"],
    },
    {"model": "reactions.reactionbutton", "exclude_fields": ["reactions"]},
    "speaker.speakersystemroles",
    {
        "model": "speaker.speakerlistsystem",
        "include_fields": [
            "state",
            "title",
            "meeting",
            "method_name",
            "settings_data",
            "safe_positions",
            "meeting_roles_to_speaker",
        ],
    },
)


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

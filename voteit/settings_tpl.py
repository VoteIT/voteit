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
    # "oauth2_provider.middleware.OAuth2TokenMiddleware",  # FIXME
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # FIXME Dev only?
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Installed apps
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
    "envelope.app.online_channel",
    "envelope.app.user_channel",
    "envelope",
    "corsheaders",
    "auditlog",
    "django_rq",
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
}
# Auditlog
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
        "include_fields": ["state", "used_by", "meeting", "roles", "user_data"],
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
    {
        "model": "room.room",
        "include_fields": [
            "open",
            "title",
            "meeting",
            "send_sls",
            "send_proposals",
        ],
    },
)

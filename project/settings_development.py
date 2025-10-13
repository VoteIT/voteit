import platform

from dotenv import load_dotenv

load_dotenv()
from .settings import *


CSRF_TRUSTED_ORIGINS = ["http://localhost:8080", "http://voteit.localhost:8080"]
CHANNEL_LAYERS["default"]["CONFIG"]["hosts"] = [("127.0.0.1", 6379)]
DATABASES["default"]["HOST"] = "localhost"
MEETING_DIALECTS_DIR = os.path.join(BASE_DIR, "src", "dialect_configs", "dialects")

# Make sure all use same connection to enable us to use one worker when developing
for qname in {"default", ENVELOPE_TIMESTAMP_QUEUE, ENVELOPE_CONNECTIONS_QUEUE}:
    RQ_QUEUES[qname] = {"HOST": "localhost", "DB": 1, "PORT": 6379}


if platform.system() == "Darwin":
    RQ = {"WORKER_CLASS": "rq.SimpleWorker"}

VERBOSE_PERMISSION_LOG = True
PERMISSON_LOG_FAIL_ONLY = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = True
ALLOWED_HOSTS = ["*"]
LOGGING["loggers"]["voteit"]["level"] = "DEBUG"
LOGGING["loggers"]["envelope"]["level"] = "DEBUG"
LOGGING["handlers"]["console"]["formatter"] = "rq_console"

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
    "rest_framework.renderers.BrowsableAPIRenderer"
)

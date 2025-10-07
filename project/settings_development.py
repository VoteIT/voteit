import platform

from dotenv import load_dotenv

load_dotenv()
from .settings import *


INSTALLED_APPS += [
    "hijack",
    "hijack.contrib.admin",
]
MIDDLEWARE += [
    "hijack.middleware.HijackUserMiddleware",
]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8080", "http://voteit.localhost:8080"]
CHANNEL_LAYERS["default"]["CONFIG"]["hosts"] = [("127.0.0.1", 6379)]
DATABASES["default"]["HOST"] = "localhost"
RQ_QUEUES["default"]["HOST"] = "localhost"
RQ_QUEUES["conn"]["HOST"] = "localhost"
RQ_QUEUES["ts"]["HOST"] = "localhost"

if platform.system() == "Darwin":
    RQ = {"WORKER_CLASS": "rq.SimpleWorker"}

DEBUG = True
VERBOSE_PERMISSION_LOG = True
PERMISSON_LOG_FAIL_ONLY = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = True
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:8080",
#     "http://127.0.0.1:8080",
#     ID_HOST,
# ]
ALLOWED_HOSTS = ["*"]
LOGGING["loggers"]["voteit"]["level"] = "DEBUG"
LOGGING["loggers"]["envelope"]["level"] = "DEBUG"
LOGGING["handlers"]["console"]["formatter"] = "rq_console"

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
    "rest_framework.renderers.BrowsableAPIRenderer"
)

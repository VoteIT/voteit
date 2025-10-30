from .settings import *

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

MIDDLEWARE.append("social_django.middleware.SocialAuthExceptionMiddleware")

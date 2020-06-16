from django.contrib.auth.models import User
from django.db.models import Model


def is_author(user: User, instance: Model):
    return getattr(instance, "author", object()) == user

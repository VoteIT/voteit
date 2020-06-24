from django.dispatch import Signal

role_added = Signal(providing_args=["sender", "instance", "users"])
role_removed = Signal(providing_args=["sender", "instance", "users"])

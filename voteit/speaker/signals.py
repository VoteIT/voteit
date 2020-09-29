from django.dispatch import Signal

list_updated = Signal(providing_args=["sender", "instance", "queue"])

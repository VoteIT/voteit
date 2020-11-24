from django.dispatch import Signal

#role_added = Signal(providing_args=["sender", "instance", "users"])
#role_removed = Signal(providing_args=["sender", "instance", "users"])


roles_added = Signal(providing_args=["sender", "instance", "roles"])
roles_removed = Signal(providing_args=["sender", "instance", "roles"])

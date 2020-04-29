from django.dispatch import Signal


before_transition = Signal(providing_args=["context", "user", "transition"])
after_transition = Signal(providing_args=["context", "user", "transition"])

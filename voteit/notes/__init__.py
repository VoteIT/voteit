from django.db.models import TextChoices


class NoteIntent(TextChoices):
    BLANK = ""
    APPROVE = "a"
    DENY = "d"

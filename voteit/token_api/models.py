from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from rest_framework_api_key.models import AbstractAPIKey
from rules.contrib.models import RulesModelMixin

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting
from voteit.token_api.validators import normalize_scopes
from voteit.token_api.validators import validate_api_key_scopes


def create_api_key_user(meeting: Meeting):
    """Create a dedicated inactive user for an API key so auditlog entries are attributable."""
    User = get_user_model()
    user = User(
        username=f"apikey-{uuid4().hex}",
        organisation_id=meeting.organisation_id,
        is_active=False,
    )
    user.set_unusable_password()
    user.save()
    return user


class MeetingAPIKey(RulesModelMixin, MeetingContext, AbstractAPIKey):
    meeting: Meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scopes = models.JSONField(
        default=list, blank=True, validators=[validate_api_key_scopes]
    )
    last_used = models.DateTimeField(null=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "scopes" in update_fields:
            self.scopes = normalize_scopes(self.scopes)
        super().save(*args, **kwargs)

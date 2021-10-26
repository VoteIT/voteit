from __future__ import annotations
from typing import TYPE_CHECKING

from django.core.mail import send_mail
from django.utils.translation import gettext_lazy as _
from pydantic import EmailStr
from pydantic import validator
from pydantic.main import BaseModel
from voteit.access_policy.abcs import InviteDispatcher
from voteit.access_policy.registries import invite_data
from voteit.access_policy.registries import invite_dispatchers

if TYPE_CHECKING:
    from voteit.access_policy.models import MeetingInvite


@invite_data
class Email(BaseModel):
    email: EmailStr

    @validator("email")
    def transform_email(cls, v: str):
        return v.lower()


@invite_dispatchers
class EmailDispatcher(InviteDispatcher):
    title = _("Send email")
    name = "send_email"
    scope = "email"

    def send(self, invite: MeetingInvite) -> bool:
        email = invite.get_scope_value(self.scope)
        if not email:
            return False

        subject = self.dispatch.subject
        if not subject:
            subject = _("Meeting invitation to %(title)s") % {
                "title": self.dispatch.meeting.title
            }
        from_email = None  # From default
        recipient_list = [email]
        # FIXME: Send html variant?
        return send_mail(subject, self.dispatch.body, from_email, recipient_list)

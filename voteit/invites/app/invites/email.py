from __future__ import annotations
from typing import TYPE_CHECKING

from django.core.mail import send_mail
from django.utils.translation import gettext_lazy as _
from pydantic import EmailStr
from pydantic import validator
from pydantic.main import BaseModel

from voteit.invites.abcs import InviteDispatcher
from voteit.invites.registries import invite_data

from voteit.invites.registries import invite_dispatchers

if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite


@invite_data
class Email(BaseModel):
    """
    Email handles quite differently now...

    >>> Email(email="  bjÖRn@hej.se")
    Email(email='björn@hej.se')

    >>> Email(email="  bjÖRn@åhlens.nu")
    Email(email='björn@åhlens.nu')

    >>> Email(email=" Björn <bjÖRn@åhlens.nu>")
    Email(email='björn@åhlens.nu')

    >>> Email(email="  bjÖRn@hej£.nu")
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    email: EmailStr

    @validator("email")
    def transform_email(cls, v: str):
        return v.lower()


@invite_dispatchers
class EmailDispatcher(InviteDispatcher):
    title = _("Send email")
    name = "send_email"
    type = "email"

    def send(self, invite: MeetingInvite) -> bool:
        subject = self.dispatch.subject
        if not subject:
            subject = _("Meeting invitation to %(title)s") % {
                "title": self.dispatch.meeting.title
            }
        from_email = None  # From default
        recipient_list = [invite.invite_data]
        # FIXME: Send html variant?
        return send_mail(subject, self.dispatch.body, from_email, recipient_list)

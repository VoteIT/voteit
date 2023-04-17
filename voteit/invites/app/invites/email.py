from __future__ import annotations
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from pydantic import EmailStr
from pydantic import validator
from pydantic.main import BaseModel

from voteit.invites.abcs import InviteDataAdapter
from voteit.invites.registries import invite_adapter_registry


if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite


class EmailSchema(BaseModel):
    email: EmailStr | None

    @validator("email")
    def transform_email(cls, v: str):
        return v.lower().strip()


@invite_adapter_registry
class InviteEmail(InviteDataAdapter):
    """
    >>> InviteEmail.columns
    ['email']
    """

    name = "email"
    schema = EmailSchema
    title = _("Email")


# @invite_dispatchers
# class EmailDispatcher(InviteDispatcher):
#     title = _("Send email")
#     name = "send_email"
#     type = "email"
#
#     def send(self, invite: MeetingInvite) -> bool:
#         subject = self.dispatch.subject
#         if not subject:
#             subject = _("Meeting invitation to %(title)s") % {
#                 "title": self.dispatch.meeting.title
#             }
#         from_email = None  # From default
#         recipient_list = [invite.invite_data]
#         # FIXME: Send html variant?
#         return send_mail(subject, self.dispatch.body, from_email, recipient_list)

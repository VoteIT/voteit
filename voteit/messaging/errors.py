from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from django.utils.translation import gettext as _
from pydantic import validator
from voteit.core.permissions import Permission
from voteit.messaging.abcs import BaseError
from voteit.messaging.abcs import ErrorSchema
from voteit.messaging.decorators import outgoing


@outgoing
class GenericError(BaseError):
    name = "error.generic"


class ValidationErrorSchema(ErrorSchema):
    errors: List[Dict]


@outgoing
class ValidationErrorMsg(BaseError):
    name = "error.validation"
    schema = ValidationErrorSchema
    data: ValidationErrorSchema
    default_msg = _("Validation error")


class UnauthorizedSchema(ErrorSchema):
    """
    Serializable error message/exception that might handle Permission types

    >>> from voteit.meeting.permissions import MeetingPermissions
    >>> err = UnauthorizedSchema(permission=MeetingPermissions.ADD)
    >>> err.json()
    '{"msg": null, "permission": "meeting.add_meeting"}'
    """

    permission: Optional[str]

    class Config:
        arbitrary_types_allowed = True

    @validator("permission", pre=True)
    def change_permission(cls, v):
        if isinstance(v, Permission):
            return str(v)
        return v


@outgoing
class UnauthorizedError(BaseError):
    """ Pretty much HTTP 403 """

    name = "error.unauthorized"
    schema = UnauthorizedSchema
    data: UnauthorizedSchema
    default_msg = _("Unauthorized")


@outgoing
class NotFoundError(BaseError):
    """ Pretty much HTTP 404 """

    name = "error.not_found"
    default_msg = _("Not found")


@outgoing
class BadRequestError(BaseError):
    """ Pretty much HTTP 400"""

    name = "error.bad_request"
    default_msg = _("Bad request")

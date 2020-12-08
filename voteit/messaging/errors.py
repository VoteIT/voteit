from typing import Optional, List, Dict

from pydantic import ValidationError
from django.utils.translation import gettext as _
from voteit.messaging.abcs import BaseError, ErrorSchema
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
    permission:str


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

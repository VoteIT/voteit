from contextlib import suppress

from pydantic import field_validator, BaseModel
from django.utils.translation import gettext_lazy as _

from voteit.invites.abcs import InviteUserDataAdapter
from voteit.invites.registries import invite_adapter_registry


with suppress(ImportError):
    from personnummer.personnummer import Personnummer
    from personnummer.personnummer import PersonnummerException

    # @invite_data
    class SwedishSSN(BaseModel):
        """
        Handles invites to Swedish social security numbers (personnummer)

        >>> SwedishSSN(swedish_ssn="  20121212-1212")
        SwedishSSN(swedish_ssn='201212121212')

        >>> SwedishSSN(swedish_ssn="  1212121212")
        SwedishSSN(swedish_ssn='201212121212')

        >>> SwedishSSN(swedish_ssn="20121212121")
        Traceback (most recent call last):
        ...
        pydantic.ValidationError:

        >>> SwedishSSN(swedish_ssn="99999999-9999")
        Traceback (most recent call last):
        ...
        pydantic.ValidationError:
        """

        swedish_ssn: str

        @field_validator("swedish_ssn")
        @classmethod
        def validate_ssn(cls, v: str) -> str:
            with suppress(PersonnummerException):
                return Personnummer(v.strip()).format(long_format=True)
            raise ValueError(_("Incorrect swedish personnummer"))

    @invite_adapter_registry
    class InviteSweSSN(InviteUserDataAdapter):
        """
        >>> rows = [['121212-1212    ']]
        >>> InviteSweSSN.preflight([InviteSweSSN.name], rows)
        >>> rows
        [['201212121212']]

        >>> InviteSweSSN.preflight([InviteSweSSN.name], [['boho']])
        Traceback (most recent call last):
        ...
        voteit.invites.exceptions.DataColValidationError: Column swedish_ssn (1) validation failed at rows: [1]
        """

        name = "swedish_ssn"
        title = _("Swedish social security number")
        schema = SwedishSSN

        @staticmethod
        def mask(v: str) -> str:
            """
            >>> f = InviteSweSSN.mask
            >>> f('191212121212')
            '19121212'
            """
            return v[:8]

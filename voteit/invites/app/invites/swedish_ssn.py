from contextlib import suppress

from pydantic import BaseModel
from pydantic import validator

from voteit.invites.registries import invite_data


with suppress(ImportError):
    from personnummer.personnummer import Personnummer
    from personnummer.personnummer import PersonnummerException

    @invite_data
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
        pydantic.error_wrappers.ValidationError:

        >>> SwedishSSN(swedish_ssn="99999999-9999")
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:
        """

        swedish_ssn: str

        @validator("swedish_ssn")
        def validate_ssn(cls, v: str) -> str:
            with suppress(PersonnummerException):
                return Personnummer(v.strip()).format(long_format=True)
            raise ValueError("Incorrect swedish personnummer")

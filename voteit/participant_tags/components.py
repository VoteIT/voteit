import re
from abc import ABC
from abc import abstractmethod

from pydantic import conlist
from pydantic import validator
from pydantic.main import BaseModel

from voteit.core.validators import ensure_unique
from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

tag_format = re.compile(r"^[a-z0-9_\-]{1,20}$")


class TagSettings(BaseModel):
    tags: conlist(str, min_items=1)
    many: bool = False

    @validator("tags")
    def validate_tags(cls, v: list[str]):
        """
        >>> f = TagSettings.validate_tags
        >>> f(['abc'])
        ['abc']
        >>> f(['123-_'])
        ['123-_']
        >>> f(['bröla!!!'])
        Traceback (most recent call last):
        ...
        ValueError: bröla!!! is not a valid tag
        >>> f(['abc', 'ABC'])
        Traceback (most recent call last):
        ...
        DuplicateItemsError: Items must be unique
        """
        tags = [cls.validate_tag(item) for item in v]
        return ensure_unique(tags)

    @staticmethod
    def validate_tag(v: str) -> str:
        v = v.lower()
        if tag_format.match(v):
            return v
        raise ValueError(f"{v} is not a valid tag")


class NamespacedTags(ComponentAdapter, ABC):
    schema = TagSettings

    @abstractmethod
    def namespace(self) -> str:
        """
        Namespace for the tag
        """


@meeting_components
class GenderTags(NamespacedTags):
    name = "gtags"
    title = "Gender"
    namespace = "gen"


@meeting_components
class PronounTags(NamespacedTags):
    name = "ptags"
    title = "Pronoun"
    namespace = "pron"

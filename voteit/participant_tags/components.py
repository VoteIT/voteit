import re
from abc import ABC
from abc import abstractmethod
from random import choices

from django.conf import settings
from pydantic import conlist
from pydantic import validator
from pydantic.main import BaseModel
from django.utils.translation import gettext_lazy as _
from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

tag_format = re.compile(r"^[a-z0-9_\-]{1,20}$")


class TagSettings(BaseModel):
    tags: conlist(str, min_items=1, unique_items=True)
    many: bool = False

    @validator("tags", each_item=True)
    def validate_tags(cls, v: str):
        """
        >>> f = TagSettings.validate_tags
        >>> f('abc')
        'abc'
        >>> f('123-_')
        '123-_'
        >>> TagSettings.validate_tags('bröla!!!')
        Traceback (most recent call last):
        ...
        ValueError: bröla!!! is not a valid tag
        """
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

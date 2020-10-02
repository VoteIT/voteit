from copy import deepcopy
from typing import Optional, Any
from xml.etree.ElementTree import ElementTree

from django.db.models import TextField
from django.http import HttpRequest
from lxml.etree import tostring
from lxml.html import fromstring
from lxml.html.clean import Cleaner
from voteit.richtext.registries import richtext_converters


cleaner = Cleaner(safe_attrs_only=False)


class RichTextDocument:
    document: Optional[ElementTree]

    def __init__(self, value: Optional[str]):
        if value is None or value == '':
            self.document = value
        else:
            self.document = fromstring(value).getroottree()
            for Converter in richtext_converters.values():
                Converter().to_internal(self.document)

    @property
    def db_value(self) -> Optional[str]:
        if self.document is None or self.document == '':
            return self.document
        return tostring(self.document, encoding='unicode')

    def render(self, request: Optional[HttpRequest] = None) -> Optional[str]:
        if self.document is None or self.document == '':
            return self.document
        doc = deepcopy(self.document)
        for Converter in richtext_converters.values():
            Converter().to_external(doc, request)
        return tostring(doc.getroot()[0][0], encoding='unicode')  # TODO Find correct first div in nice way

    def __str__(self) -> str:
        return self.render()

    def __bool__(self) -> bool:
        return bool(self.document)

    def __eq__(self, o: object) -> bool:
        return str(self) == o


# TODO: Very untested right now
class RichTextField(TextField):
    """
    TextField that allows converting into an internal representation of HTML. Will clean HTML.
    Content converters allow filtering content based on request.
    Access external representation by calling .render(value, request).
    """

    def clean(self, value, model_instance):
        # TODO: Test this...
        value = cleaner.clean_html(value)
        return super().clean(value, model_instance)

    def from_db_value(self, value, expression, connection):
        return RichTextDocument(value)

    def get_prep_value(self, value: Optional[RichTextDocument]) -> Optional[str]:
        if not isinstance(value, RichTextDocument):
            value = RichTextDocument(value)
        return value.db_value

    def to_python(self, value: str) -> RichTextDocument:
        return RichTextDocument(value)

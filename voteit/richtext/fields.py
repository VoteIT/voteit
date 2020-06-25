from typing import Optional
from xml.etree.ElementTree import ElementTree

from django.db.models import TextField
from django.http import HttpRequest
from lxml.etree import tostring
from lxml.html import fromstring
from lxml.html.clean import clean_html
from voteit.richtext.registries import richtext_converters


# TODO: Very untested right now
class RichTextField(TextField):
    """
    TextField that allows converting into an internal representation of HTML. Will clean HTML.
    Content converters allow filtering content based on request.
    Access external representation by calling .render(value, request).
    """

    def clean(self, value, model_instance):
        # TODO: Test this...
        value = clean_html(value)
        return super().clean(value, model_instance)

    def get_prep_value(self, value: ElementTree) -> str:
        for Converter in richtext_converters.values():
            Converter().to_internal(value)
        return tostring(value, encoding='unicode')

    def to_python(self, value: str) -> ElementTree:
        # TODO: Reason about root node
        return fromstring(value).getroottree()

    def render(self, value: ElementTree, request: Optional[HttpRequest]) -> str:
        # FIXME: Can this even live here?
        for Converter in richtext_converters.values():
            Converter().to_external(value, request)
        return tostring(value, encoding='unicode')

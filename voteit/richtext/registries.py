from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Optional, Iterable
from xml.etree.ElementTree import ElementTree, Element

from django.contrib.auth.models import User
from django.http import HttpRequest
from django.utils.text import gettext_lazy as _

from voteit.core.component import Registry


class RichTextConverter(ABC):
    strip_text: bool = True
    allowed_attributes: Iterable[str] = ()
    identifier: Optional[str] = None

    @staticmethod
    def convert_to_internal(
            document: ElementTree,
            registry: Registry = None) -> None:
        converter_registry = registry or richtext_converters
        for Converter in converter_registry.values():
            Converter().to_internal(document)

    @staticmethod
    def convert_to_external(
            document: ElementTree,
            request: Optional[HttpRequest] = None,
            registry: Registry = None) -> None:
        converter_registry = registry or richtext_converters
        for Converter in converter_registry.values():
            Converter().to_external(document, request)

    @property
    @abstractmethod
    def internal_tag_name(self) -> str:
        pass

    @property
    @abstractmethod
    def external_tag_name(self) -> str:
        pass

    def get_context(self, element):
        """Allow getting context once and reusing in different methods."""
        return {}

    def to_internal(self, document: ElementTree):
        for element in document.findall(f'//{self.identifier or self.external_tag_name}'):
            element.tag = self.internal_tag_name
            for k in element.attrib:
                if k not in self.allowed_attributes:
                    del element.attrib[k]
            if self.strip_text:
                element.text = None

    def to_external(self, document: ElementTree, request: Optional[HttpRequest] = None):
        for element in document.findall(f'//{self.internal_tag_name}'):
            context = self.get_context(element)
            element.tag = self.external_tag_name
            element.text = self.get_text(element, context)
            element.attrib.update(self.get_attributes(element, context))

    def get_text(self, element: Element, context: dict) -> str:
        return element.text

    def get_attributes(self, element: Element, context: dict) -> dict:
        return {}


richtext_converters = Registry(RichTextConverter)


@richtext_converters
class TestUserConverter(RichTextConverter):
    identifier = 'a[@data-user-id]'
    internal_tag_name = 'user'
    external_tag_name = 'a'
    allowed_attributes = 'data-user-id',

    def get_context(self, element) -> dict:
        context = super().get_context(element)
        with suppress(User.DoesNotExist):
            context['user'] = User.objects.get(pk=element.attrib['data-user-id'])
        return context

    def get_text(self, element, context: dict):
        user = context.get('user')
        if user:
            return user.get_full_name()
        return str(_('Unknown user'))

    def get_attributes(self, element, context: dict):
        user = context.get('user')
        if user:
            return {
                'href': f'/user-info-url/{user.pk}'  # TODO
            }
        return {}

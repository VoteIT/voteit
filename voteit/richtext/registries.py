from abc import ABC, abstractmethod
from typing import Optional, Iterable
from xml.etree.ElementTree import ElementTree, Element

from django.http import HttpRequest
from voteit.core.component import Registry


class RichTextConverter(ABC):
    strip_text: bool = True
    allowed_attributes: Iterable[str] = ()
    identifier: Optional[str] = None

    @staticmethod
    def convert_to_internal(document: ElementTree) -> None:
        for Converter in richtext_converters.values():
            Converter().to_internal(document)

    @staticmethod
    def convert_to_external(document: ElementTree, request: Optional[HttpRequest] = None) -> None:
        for Converter in richtext_converters.values():
            Converter().to_external(document, request)

    @property
    @abstractmethod
    def internal_tag_name(self) -> str:
        pass

    @property
    @abstractmethod
    def external_tag_name(self) -> str:
        pass

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
            element.tag = self.external_tag_name
            element.text = self.get_text(element)
            element.attrib.update(self.get_attributes(element))

    def get_text(self, element: Element) -> str:
        return element.text

    def get_attributes(self, element: Element) -> dict:
        return {}


richtext_converters = Registry(RichTextConverter)

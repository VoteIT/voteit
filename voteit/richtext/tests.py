from django.test import TestCase
from lxml.html import tostring, fromstring

from voteit.core.component import Registry

from .registries import RichTextConverter


richtext_test_converters = Registry(RichTextConverter)


class TestRichTextField(TestCase):
    @richtext_test_converters
    class TestSimpleConverter(RichTextConverter):
        strip_text = False
        internal_tag_name = 'b'
        external_tag_name = 'a'

    @richtext_test_converters
    class TestSimpleConverter2(RichTextConverter):
        internal_tag_name = 'y'
        external_tag_name = 'x'

    class TestUserConverter(RichTextConverter):
        identifier = 'a[@data-user-id]'
        internal_tag_name = 'user'
        external_tag_name = 'a'
        allowed_attributes = 'data-user-id',

        def get_text(self, element, context):
            return 'User Name'

        def get_attributes(self, element, context):
            return {
                'href': '/elsewhere'
            }

    def setUp(self) -> None:
        pass

    def _test_internal_external(self, input, expected_internal, expected_external, Converter=None):
        document = fromstring(input).getroottree()
        if Converter:
            converter = Converter()
            converter.to_internal(document)
            self.assertInHTML(expected_internal, tostring(document, encoding='unicode'))
            converter.to_external(document)
            self.assertInHTML(expected_external, tostring(document, encoding='unicode'))
        else:
            RichTextConverter.convert_to_internal(document, registry=richtext_test_converters)
            self.assertInHTML(expected_internal, tostring(document, encoding='unicode'))
            RichTextConverter.convert_to_external(document, registry=richtext_test_converters)
            self.assertInHTML(expected_external, tostring(document, encoding='unicode'))

    def test_user_conversion(self):
        self._test_internal_external(
            input='<html><h2>A user</h2><p><a href="/somewhere" data-user-id="123">User thing</a></p></html>',
            expected_internal='<user data-user-id="123"></user>',
            expected_external='<a data-user-id="123" href="/elsewhere">User Name</a>',
            Converter=self.TestUserConverter,
        )

    def test_simple_conversion(self):
        self._test_internal_external(
            input='<html><a href="/somewhere">Text</a></html>',
            expected_internal='<b>Text</b>',
            expected_external='<a>Text</a>',
            Converter=self.TestSimpleConverter,
        )

    def test_registry_all(self):
        self.assertEqual(len(richtext_test_converters), 2)
        self._test_internal_external(
            input='<html><a>Ada</a><x>Lovelace</x></html>',
            expected_internal='<b>Ada</b><y></y>',
            expected_external='<a>Ada</a><x></x>',
        )

from abc import ABC, abstractmethod

from django.test import TestCase


class FactoryRegistryTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.component import Registry

        return Registry

    def test_registration(self):
        registry = self._cut(object)

        @registry
        class HelloClass:
            pass

        self.assertIn("helloclass", registry)

    def test_registration_named(self):
        registry = self._cut(object)

        @registry
        class HelloClass:
            name = "hello"

        self.assertIn("hello", registry)

    def test_registration_required_base(self):
        class A:
            pass

        registry = self._cut(A)

        @registry
        class B(A):
            pass

        try:

            @registry
            class C:
                pass

            self.fail("TypeError not raised")
        except TypeError:
            pass

    def test_registration_bad_implementation(self):
        class A(ABC):

            @abstractmethod
            def important(self):
                pass

        class B(A):
            pass

        registry = self._cut(A)

        self.assertRaises(TypeError, registry, B)

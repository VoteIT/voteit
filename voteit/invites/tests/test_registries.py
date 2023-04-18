# from django.apps import apps
# from django.core.exceptions import ImproperlyConfigured
# from django.test import TestCase
# from pydantic import BaseModel
#
# from voteit.invites.abcs import InviteAnnotationAdapter
# from voteit.invites.abcs import InviteDataAdapter
# from voteit.invites.utils import get_invite_adapter_registry
# from voteit.invites.utils import get_invite_annotation_registry
#
#
# class BadSchema(BaseModel):
#     boho: int
#
#
# class Bad:
#     name = "bad"
#     schema = BadSchema
#
#
# class BadDataThingy(Bad, InviteDataAdapter):
#     ...
#
#
# class BadAnnotationThingy(Bad, InviteAnnotationAdapter):
#     ...
#
#
# class RegistriesTests(TestCase):
#     @classmethod
#     def tearDownClass(cls):
#         del get_invite_adapter_registry()["bad"]
#         del get_invite_annotation_registry()["bad"]
#         super().tearDownClass()
#
#     def test_collision(self):
#         get_invite_adapter_registry()(BadDataThingy)
#         get_invite_annotation_registry()(BadAnnotationThingy)
#         app = apps.get_app_config("invites")
#         with self.assertRaises(ImproperlyConfigured) as cm:
#             app.ready()
#         self.assertEqual(
#             "voteit.invites.registries invite_annotations_registry and invite_adapter_registry contain intersecting keys: {'bad'}",
#             str(cm.exception),
#         )

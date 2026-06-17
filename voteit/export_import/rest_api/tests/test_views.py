import os
import tempfile

import yaml
from django.core.cache import cache
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.proposal.models import Proposal
from voteit.export_import.tests import FIXTURES_DIR
from voteit.export_import.rest_api.lock import import_lock
from voteit.export_import.rest_api.lock import import_preview_lock
from voteit.export_import.utils import MAX_IMPORT_BYTES
from voteit.export_import.utils import MAX_UNSIGNED_IMPORT_BYTES
from voteit.export_import.utils import sign_payload

User = get_user_model()


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class MeetingDataImportViewTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)

    def test_empty_file(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "empty.txt"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "The submitted file is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_junk_file(self):
        # A small file with no sign header is allowed through the validator but
        # rejected because it isn't valid YAML key-value data.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "junk.txt"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "Import file malformed",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_bad_version(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "bad_version.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "Wrong file version",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_empty_import(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "empty_import.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(
            {"file": ["File doesn't contain any agenda items or groups"]},
            response.json(),
        )

    def test_empty_sign(self):
        # A small file with an empty/invalid signature is allowed through the
        # validator (below the unsigned size limit). The import then fails because
        # the file contains no agenda items or groups.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "empty_sign.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(
            {"file": ["File doesn't contain any agenda items or groups"]},
            response.json(),
        )

    def test_unsigned_file_too_large_rejected(self):
        # A file without a valid signature that exceeds MAX_UNSIGNED_IMPORT_BYTES
        # must be rejected before any parsing takes place.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        oversized = b"x" * (MAX_UNSIGNED_IMPORT_BYTES + 1)
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            tmp.write(oversized)
            tmp.seek(0)
            response = self.client.post(url, data={"file": tmp}, format="multipart")
        self.assertContains(
            response,
            "Unsigned file too large",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_ais_and_groups(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(
            {
                "agenda_items": 3,
                "diff_proposals": 0,
                "discussion_posts": 0,
                "groups": 1,
                "proposals": 1,
                "text_documents": 0,
                "reactions": 0,
                "buttons": 0,
                "buttons_reused": 0,
                "groups_reused": 0,
                "notes": 0,
            },
            response.json(),
        )
        self.assertEqual(
            ["Crisps", "Hot dogs", "Pickles"],
            list(
                self.meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )
        self.assertEqual(
            ["The Hellos"],
            list(self.meeting.groups.values_list("title", flat=True).order_by("title")),
        )

    def test_ais_and_groups_skip_proposals(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "include_proposals": False}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(
            {
                "agenda_items": 3,
                "diff_proposals": 0,
                "discussion_posts": 0,
                "groups": 1,
                "proposals": 0,
                "text_documents": 0,
                "buttons": 0,
                "reactions": 0,
                "buttons_reused": 0,
                "groups_reused": 0,
                "notes": 0,
            },
            response.json(),
        )

    def test_ais_and_groups_clear_and_skip_groups(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url,
                data={"file": f, "include_groups": False, "clear_group_authors": True},
                format="multipart",
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(0, self.meeting.groups.count())
        self.assertEqual(1, Proposal.objects.all().count())
        prop = Proposal.objects.first()
        self.assertEqual(None, prop.meeting_group)

    def test_combined_reactions_excluded_by_default(self):
        # include_reactions defaults to False, so reactions are not imported even if present in the file.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(
            os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"), "rb"
        ) as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(0, response.json()["reactions"])

    def test_combined_reactions_included(self):
        # When include_reactions=True, reactions from the fixture are imported.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(
            os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"), "rb"
        ) as f:
            response = self.client.post(
                url, data={"file": f, "include_reactions": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(4, response.json()["reactions"])

    def test_combined_buttons_excluded(self):
        # include_buttons=False skips both buttons and their reactions.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(
            os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"), "rb"
        ) as f:
            response = self.client.post(
                url, data={"file": f, "include_buttons": False}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertEqual(0, data["buttons"])
        self.assertEqual(0, data["reactions"])

    def test_buttons_reactions_bad_combination(self):
        # include_buttons=False with include_reactions=True is rejected because reactions require buttons.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url,
                data={"file": f, "include_buttons": False, "include_reactions": True},
                format="multipart",
            )
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(
            {
                "include_reactions": "Buttons are needed to set reactions - change 'include_buttons'"
            },
            response.json(),
        )

    def test_ais_and_groups_bad_combination(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url,
                data={"file": f, "include_groups": False},
                format="multipart",
            )
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertEqual(
            {
                "include_groups": "Groups are needed to set group authors - change 'clear_group_authors' or 'include_groups'"
            },
            response.json(),
        )

    def _signed_tempfile(self, content: str):
        payload = content.encode()
        signed = b"sign: " + sign_payload(payload).encode() + b"\n" + payload
        tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False)
        tmp.write(signed)
        tmp.seek(0)
        return tmp

    def test_yaml_alias_rejected_on_import(self):
        # A YAML file with anchors/aliases must be rejected to prevent alias-expansion attacks.
        alias_yaml = "a: &anchor value\nb: *anchor\n"
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with self._signed_tempfile(alias_yaml) as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "YAML aliases are not permitted",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_preview_unsigned_file_reports_lower_limit(self):
        # A small unsigned file is accepted; preview reports signature_valid=False
        # and the tighter unsigned size_limit.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        unsigned_yaml = (
            b"meta:\n  version: 1\nagenda_items:\n  - title: Hi\n    body: ''\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            tmp.write(unsigned_yaml)
            tmp.seek(0)
            response = self.client.post(
                url, data={"file": tmp, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertFalse(data["signature_valid"])
        self.assertEqual(MAX_UNSIGNED_IMPORT_BYTES, data["size_limit"])
        # Nothing was actually imported.
        self.assertEqual(0, self.meeting.agenda_items.count())

    def test_yaml_alias_rejected_on_preview(self):
        alias_yaml = "a: &anchor value\nb: *anchor\n"
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with self._signed_tempfile(alias_yaml) as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertContains(
            response,
            "YAML aliases are not permitted",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_ais_and_groups_preview(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertIn("groups", data)
        self.assertEqual(
            [{"title": "The Hellos", "groupid": "the-hellos"}], data["groups"]
        )
        self.assertIn("agenda_items", data)
        self.assertEqual(3, len(data["agenda_items"]))
        self.assertEqual(
            {
                "body": "could be tasty",
                "proposals": [
                    {
                        "body": "as long as they're vegetarian",
                        "meeting_group": "the-hellos",
                    }
                ],
                "state": "upcoming",
                "title": "Pickles",
            },
            data["agenda_items"][0],
        )
        # Signature metadata
        self.assertTrue(data["signature_valid"])
        self.assertEqual(MAX_IMPORT_BYTES, data["size_limit"])
        # Nothing was actually imported.
        self.assertEqual(0, self.meeting.agenda_items.count())

    def test_preview_does_not_require_agenda_items_or_groups(self):
        # Unlike a real import, preview of an empty file is not rejected.
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "empty_import.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class MeetingDataExportViewTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.organisation = cls.meeting.organisation
        cls.new_meeting = cls.organisation.meetings.create()
        cls.new_meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def test_yaml(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = yaml.safe_load(response.content)
        self.assertEqual("The Hellos", data["groups"][0]["title"])

    def test_yaml_round_trip(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.new_meeting.pk})
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp_file:
            tmp_file.write(response.content)
            tmp_file.seek(0)
            response = self.client.post(
                url, data={"file": tmp_file}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(
            ["Crisps", "Hot dogs", "Pickles"],
            list(
                self.new_meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )

    def test_yaml_exclude_groups(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.get(
            url, data={"include_groups": 0, "clear_group_authors": 1}
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = yaml.safe_load(response.content)
        self.assertEqual([], data["groups"])

    def test_yaml_exclude_groups_bad_combination(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.get(url, data={"include_groups": 0})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        data = response.json()
        self.assertEqual(
            {
                "include_groups": "Groups are needed to set group authors - change 'clear_group_authors' or 'include_groups'"
            },
            data,
        )


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class CloneViewTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.organisation = cls.meeting.organisation
        cls.target_meeting = cls.organisation.meetings.create()
        cls.target_meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.ongoing_meeting = cls.organisation.meetings.create(state="ongoing")
        cls.ongoing_meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def setUp(self):
        self.client.force_login(self.moderator)
        # Ensure a session key so lock tests work.
        self.client.get(reverse("meeting-data-list"))
        self.session_key = self.client.session.session_key

    def tearDown(self):
        cache.clear()

    def test_clone_success(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url, data={"source": self.meeting.pk}, format="json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertGreater(data["agenda_items"], 0)
        self.assertIsNone(cache.get(import_lock._processing_key(self.session_key)))
        self.assertIsNotNone(cache.get(import_lock._cooldown_key(self.session_key)))

    def test_clone_target_not_upcoming_rejected(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.ongoing_meeting.pk})
        response = self.client.post(
            url, data={"source": self.meeting.pk}, format="json"
        )
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn("upcoming", response.json()["detail"])

    def test_clone_unknown_source_rejected(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(url, data={"source": 99999}, format="json")
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        self.assertIn("source", response.json())

    def test_clone_include_notes(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url,
            data={"source": self.meeting.pk, "include_notes": True},
            format="json",
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertEqual(3, data["notes"])

    def test_clone_exclude_notes_by_default(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url, data={"source": self.meeting.pk}, format="json"
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertEqual(0, data["notes"])

    def test_clone_blocked_by_processing_lock(self):
        cache.add(import_lock._processing_key(self.session_key), 1, 60)
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url, data={"source": self.meeting.pk}, format="json"
        )
        self.assertEqual(status.HTTP_409_CONFLICT, response.status_code)

    def test_clone_preview(self):
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url,
            data={"source": self.meeting.pk, "preview": True},
            format="json",
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertIn("groups", data)
        self.assertIn("agenda_items", data)
        self.assertGreater(len(data["agenda_items"]), 0)
        # Nothing was actually cloned into the target meeting.
        self.assertEqual(0, self.target_meeting.agenda_items.count())
        self.assertEqual(0, self.target_meeting.groups.count())

    def test_clone_preview_uses_preview_lock(self):
        # The preview lock has no cooldown, so a second preview can run right away...
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url,
            data={"source": self.meeting.pk, "preview": True},
            format="json",
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertIsNone(
            cache.get(import_preview_lock._cooldown_key(self.session_key))
        )
        # ...and it doesn't interfere with the real-import lock.
        self.assertIsNone(cache.get(import_lock._processing_key(self.session_key)))
        self.assertIsNone(cache.get(import_lock._cooldown_key(self.session_key)))

    def test_clone_preview_blocked_by_preview_processing_lock(self):
        cache.add(import_preview_lock._processing_key(self.session_key), 1, 60)
        url = reverse("meeting-data-clone", kwargs={"pk": self.target_meeting.pk})
        response = self.client.post(
            url,
            data={"source": self.meeting.pk, "preview": True},
            format="json",
        )
        self.assertEqual(status.HTTP_409_CONFLICT, response.status_code)


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class ImportLockTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)

    def setUp(self):
        self.client.force_login(self.moderator)
        # Ensure a session key exists before each test.
        self.client.get(reverse("meeting-data-list"))
        self.session_key = self.client.session.session_key

    def tearDown(self):
        cache.clear()

    def test_lock_prevents_concurrent_import(self):
        cache.add(import_lock._processing_key(self.session_key), 1, 60)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_409_CONFLICT, response.status_code)
        self.assertIn("already in progress", response.json()["detail"])

    def test_cooldown_prevents_immediate_resubmit(self):
        cache.add(import_lock._cooldown_key(self.session_key), 1, 60)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_429_TOO_MANY_REQUESTS, response.status_code)
        self.assertIn("wait", response.json()["detail"])

    def test_lock_not_consumed_by_validation_error(self):
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "empty.txt"), "rb") as f:
            self.client.post(url, data={"file": f}, format="multipart")
        self.assertIsNone(cache.get(import_lock._processing_key(self.session_key)))

    def test_preview_uses_separate_lock_without_cooldown(self):
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertIsNone(
            cache.get(import_preview_lock._processing_key(self.session_key))
        )
        self.assertIsNone(
            cache.get(import_preview_lock._cooldown_key(self.session_key))
        )
        # Doesn't touch the real-import lock either.
        self.assertIsNone(cache.get(import_lock._processing_key(self.session_key)))
        self.assertIsNone(cache.get(import_lock._cooldown_key(self.session_key)))

    def test_preview_blocked_by_preview_processing_lock(self):
        cache.add(import_preview_lock._processing_key(self.session_key), 1, 60)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_409_CONFLICT, response.status_code)

    def test_preview_not_blocked_by_real_import_cooldown(self):
        # A cooldown on the real-import lock must not block previews.
        cache.add(import_lock._cooldown_key(self.session_key), 1, 60)
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(
                url, data={"file": f, "preview": True}, format="multipart"
            )
        self.assertEqual(status.HTTP_200_OK, response.status_code)

    def test_lock_released_after_successful_import(self):
        url = reverse("meeting-data-import-file", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES_DIR, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.post(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertIsNone(cache.get(import_lock._processing_key(self.session_key)))
        self.assertIsNotNone(cache.get(import_lock._cooldown_key(self.session_key)))

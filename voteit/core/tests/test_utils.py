from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.organisation.models import Organisation

User = get_user_model()

evil_text_snippet = """
    <a href="javascript:evil_function()">a link</a>
    <a href="#" onclick="evil_function()">another link</a>
    <p onclick="evil_function()">a paragraph</p>
    <div style="display: none">secret EVIL!</div>
    <object> of EVIL! </object>
    <iframe src="evil-site"></iframe>
    <form action="evil-site">
      Password: <input type="password" name="password">
    </form>
    <blink>annoying EVIL!</blink>
    <a href="evil-site">spam spam SPAM!</a>
    <image src="evil!">"""

evil_full_example = (
    """
 <html>
  <head>
    <script type="text/javascript" src="evil-site"></script>
    <link rel="alternate" type="text/rss" src="evil-rss">
    <style>
      body {background-image: url(javascript:do_evil)};
      div {color: expression(evil)};
    </style>
  </head>
  <body onload="evil_function()">
    <!-- I am interpreted for EVIL! -->
    %s
  </body>
 </html>"""
    % evil_text_snippet
)


class CleaningUtilsTests(TestCase):
    pass


class GenerateValidUseridTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="jeff", first_name="Jeff", last_name="Benzies"
        )
        self.org_user = User.objects.create(
            username="virginia",
            first_name="Virginia",
            last_name="Woolf",
            organisation=Organisation.objects.create(title="King's College"),
        )

    @property
    def _fut(self):
        from voteit.core.utils import generate_valid_userid

        return generate_valid_userid

    def test_generate(self):
        self.assertEqual(self._fut(self.user), "jeff-benzies")

    def test_generate_omit_current_user(self):
        self.user.userid = "jeff-benzies"
        self.user.save()
        self.assertEqual(self._fut(self.user), "jeff-benzies")

    def test_already_exists(self):
        User.objects.create(
            username="other",
            first_name="Jeff",
            last_name="Benzies",
            userid="jeff-benzies",
        )
        self.assertNotEqual(self._fut(self.user), "jeff-benzies")

    def test_generate_with_org(self):
        self.user.userid = "virginia-woolf"
        self.user.save()
        self.assertEqual(self._fut(self.org_user), "virginia-woolf")

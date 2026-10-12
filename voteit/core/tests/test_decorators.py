from http import HTTPStatus
from unittest.mock import Mock

from django.http import HttpRequest
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.test import Client
from django.test import SimpleTestCase
from django.test import override_settings
from django.urls import path

from voteit.core.decorators import csrf_exempt_for_origins
from voteit.core.decorators import request_origin

ALLOWED_ORIGIN = "https://widget.example.com"
OTHER_ORIGIN = "https://evil.example.com"

get_origins = Mock(return_value={ALLOWED_ORIGIN})


@csrf_exempt_for_origins(get_origins)
def widget_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """View under test: docstring and name should survive the decorator."""
    return HttpResponse(f"{args} {kwargs}")


def token_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(get_token(request))


urlpatterns = [
    path("widget/", widget_view),
    path("widget/<int:pk>/", widget_view),
    path("token/", token_view),
]


@override_settings(ROOT_URLCONF=__name__)
class CsrfExemptForOriginsTests(SimpleTestCase):
    def setUp(self):
        # The default test client disables CSRF enforcement entirely
        self.client = Client(enforce_csrf_checks=True)
        get_origins.reset_mock()

    def post(self, **extra):
        return self.client.post("/widget/", **extra)

    def csrf_token(self):
        self.client.get("/token/")
        return self.client.cookies["csrftoken"].value

    def test_allowed_origin_is_exempt(self):
        response = self.post(headers={"origin": ALLOWED_ORIGIN})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_allowed_origin_via_referer_is_exempt(self):
        response = self.post(headers={"referer": f"{ALLOWED_ORIGIN}/some/page?q=1"})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_origin_header_wins_over_referer(self):
        response = self.post(
            headers={"origin": OTHER_ORIGIN, "referer": f"{ALLOWED_ORIGIN}/page"}
        )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_other_origin_is_rejected(self):
        response = self.post(headers={"origin": OTHER_ORIGIN})
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertIn(b"CSRF", response.content)

    def test_origin_must_match_exactly(self):
        for origin in (
            f"{ALLOWED_ORIGIN}.evil.example.com",
            f"{ALLOWED_ORIGIN}:8443",
            "http://widget.example.com",
            "https://sub.widget.example.com",
            "null",
        ):
            with self.subTest(origin=origin):
                response = self.post(headers={"origin": origin})
                self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_unparseable_referer_is_rejected(self):
        response = self.post(headers={"referer": "not-a-url"})
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_no_origin_and_no_token_is_rejected(self):
        response = self.post()
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        get_origins.assert_not_called()

    def test_no_origin_with_valid_token_is_accepted(self):
        response = self.post(data={"csrfmiddlewaretoken": self.csrf_token()})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_no_origin_with_invalid_token_is_rejected(self):
        self.csrf_token()
        response = self.post(data={"csrfmiddlewaretoken": "x" * 64})
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_safe_method_is_not_rejected(self):
        response = self.client.get("/widget/")
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_view_is_marked_csrf_exempt(self):
        # Or the global CsrfViewMiddleware rejects allowed origins first
        self.assertTrue(widget_view.csrf_exempt)

    def test_view_metadata_is_preserved(self):
        self.assertEqual(widget_view.__name__, "widget_view")
        self.assertIn("View under test", widget_view.__doc__)

    def test_view_and_origins_receive_arguments(self):
        response = self.client.post("/widget/42/", headers={"origin": ALLOWED_ORIGIN})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.content, b"() {'pk': 42}")
        request = get_origins.call_args.args[0]
        self.assertIsInstance(request, HttpRequest)
        self.assertEqual({"pk": 42}, get_origins.call_args.kwargs)


class RequestOriginTests(SimpleTestCase):
    def request(self, **meta) -> HttpRequest:
        request = HttpRequest()
        request.META.update(meta)
        return request

    def test_origin_header(self):
        origin = request_origin(self.request(HTTP_ORIGIN=ALLOWED_ORIGIN))
        self.assertEqual(origin, ALLOWED_ORIGIN)

    def test_referer_fallback_drops_path_and_query(self):
        origin = request_origin(
            self.request(HTTP_REFERER=f"{ALLOWED_ORIGIN}/a/b?c=d#e")
        )
        self.assertEqual(origin, ALLOWED_ORIGIN)

    def test_no_headers(self):
        self.assertIsNone(request_origin(self.request()))

    def test_empty_headers(self):
        self.assertIsNone(request_origin(self.request(HTTP_ORIGIN="", HTTP_REFERER="")))

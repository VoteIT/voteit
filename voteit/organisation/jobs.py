from contextlib import suppress
from datetime import timedelta
from logging import getLogger

from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils.html import strip_tags
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_rq import job
from social_django.models import Code
from social_django.models import Partial
from social_django.models import UserSocialAuth

from voteit.core import RQ_LONG_QUEUE
from voteit.core.decorators import schedule_job
from voteit.organisation.models import OAuth2Provider

logger = getLogger(__name__)


@schedule_job("0 4 * * *")
def cleanup_extra_data_for_older_users(**kwargs):
    """
    We don't want to keep extra data that's unused for 1 year.
    """
    return (
        UserSocialAuth.objects.filter(modified__lt=now() - timedelta(days=365))
        .exclude(extra_data={})
        .update(extra_data={})
    )


#: How long a paused login may sit unanswered. ``clearsocial`` defaults to 14
#: days; a partial holds the provider's whole response, tokens included, and a
#: login nobody finished within a day is not going to be finished.
SOCIAL_LEFTOVER_DAYS = 1


@schedule_job("40 4 * * *")
def cleanup_social_auth_leftovers(**kwargs):
    """
    Drop paused logins and unused codes that nobody came back for.

    This is what ``manage.py clearsocial`` does, on the schedule everything else
    here runs on -- a cron entry nobody remembers to add is how a table holding
    access tokens grows forever.

    A partial is the whole pipeline frozen mid-flight, so it carries the
    provider's response and the tokens in it. Abandoning one costs the person
    nothing: they log in again and are asked again.
    """
    cutoff = now() - timedelta(days=SOCIAL_LEFTOVER_DAYS)
    partials, _ = Partial.objects.filter(timestamp__lt=cutoff).delete()
    codes, _ = Code.objects.filter(verified=False, timestamp__lt=cutoff).delete()
    if partials or codes:
        logger.info(
            "cleanup_social_auth_leftovers: %d partial(s), %d unused code(s)",
            partials,
            codes,
        )
    return partials + codes


@job(RQ_LONG_QUEUE)
def email_login_method_added(social_auth_pk: int):
    """
    Tell someone a login method was attached to their account.

    This goes to the address the account already had, never the one the new
    credential brought with it: the point is to reach the person who owns the
    account, which matters most when the connection was a mistake and they are
    not the person who just logged in.
    """
    try:
        social = UserSocialAuth.objects.select_related(
            "user", "user__organisation"
        ).get(pk=social_auth_pk)
    except UserSocialAuth.DoesNotExist:
        logger.info("email_login_method_added: %s is gone, skipping", social_auth_pk)
        return
    user = social.user
    organisation = user.organisation
    if not user.email or organisation is None:
        return
    # A provider row can be gone or its backend left out of this deployment;
    # the bare name is a worse label but still tells them which login it was.
    provider_title = social.provider
    with suppress(OAuth2Provider.DoesNotExist):
        if backend := organisation.get_provider(social.provider).backend:
            provider_title = backend.get_title()
    site_url = f"https://{organisation.host}/"
    html_body = loader.render_to_string(
        "voteit/organisation/login_method_added.html",
        context={
            "full_name": user.get_full_name() or user.username,
            "provider_title": provider_title,
            "org_title": organisation.title,
            "site_url": site_url,
            "title": _("A new login method was connected"),
        },
    )
    send_mail(
        subject=_("A new login method was connected to your account"),
        message=strip_tags(html_body),
        html_message=html_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return f"Notified {user.pk} about {social.provider} being connected."

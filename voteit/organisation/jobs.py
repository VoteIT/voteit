from datetime import timedelta

from django.utils.timezone import now
from social_django.models import UserSocialAuth

from voteit.core.decorators import schedule_job


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

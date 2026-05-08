from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("poll", "0014_backfill_voter_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="electoralregister",
            name="voters",
        ),
        migrations.DeleteModel(
            name="VoterWeight",
        ),
    ]

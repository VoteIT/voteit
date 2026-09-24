from django.db import migrations


class Migration(migrations.Migration):
    """
    The old TermsOfService and UserConsent were removed from the earlier migrations,
    so they're not in the migration state. Databases that ran the old versions still
    have the tables.
    """

    dependencies = [
        ("organisation", "0016_oauth2provider_hidden_oauth2provider_primary"),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS organisation_userconsent, "
            "organisation_termsofservice_mentions, organisation_termsofservice",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

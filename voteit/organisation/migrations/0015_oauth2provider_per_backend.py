import django.db.models.deletion
from django.db import migrations
from django.db import models


def delete_orphan_providers(apps, schema_editor):
    """
    Drop credentials belonging to no organisation.

    ``organisation`` becomes required below. Such rows were already unreachable:
    every lookup goes through ``Organisation.get_provider()``.
    """
    OAuth2Provider = apps.get_model("organisation", "OAuth2Provider")
    OAuth2Provider.objects.filter(organisation__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organisation", "0014_remove_organisation_last_modified_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="oauth2provider",
            name="provider_id",
            # Every existing row is the id proxy; it was the only backend.
            field=models.CharField(
                default="idproxy", max_length=30, verbose_name="Backend name"
            ),
        ),
        migrations.AddField(
            model_name="oauth2provider",
            name="oidc_endpoint",
            field=models.URLField(
                blank=True,
                default="",
                help_text=(
                    "OpenID Connect issuer base URL, without "
                    "/.well-known/openid-configuration. Only used by OIDC "
                    "backends, and only to override the backend's own default."
                ),
                max_length=300,
                verbose_name="OIDC issuer",
            ),
        ),
        migrations.RunPython(delete_orphan_providers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="oauth2provider",
            name="organisation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="providers",
                to="organisation.organisation",
            ),
        ),
        migrations.AddConstraint(
            model_name="oauth2provider",
            constraint=models.UniqueConstraint(
                fields=("organisation", "provider_id"), name="unique org provider_id"
            ),
        ),
    ]

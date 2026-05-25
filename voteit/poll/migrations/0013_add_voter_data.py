from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("poll", "0012_votetransfer"),
    ]

    operations = [
        migrations.AddField(
            model_name="electoralregister",
            name="voter_data",
            field=models.JSONField(default=dict),
        ),
    ]

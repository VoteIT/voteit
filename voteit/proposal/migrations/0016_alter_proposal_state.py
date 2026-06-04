from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("proposal", "0015_alter_textdocument_body"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposal",
            name="state",
            field=models.CharField(
                choices=[
                    ("published", "Published"),
                    ("retracted", "Retracted"),
                    ("voting", "Voting"),
                    ("approved", "Approved"),
                    ("denied", "Denied"),
                    ("unhandled", "Unhandled"),
                ],
                default="published",
                max_length=20,
            ),
        ),
    ]

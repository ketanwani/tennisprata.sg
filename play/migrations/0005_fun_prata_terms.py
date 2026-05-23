from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("play", "0004_profile_avatar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pratasession",
            name="prata_terms",
            field=models.CharField(
                blank=True,
                default="Optional: losing pair treats prata, teh, or just accepts light-hearted banter.",
                max_length=180,
            ),
        ),
    ]

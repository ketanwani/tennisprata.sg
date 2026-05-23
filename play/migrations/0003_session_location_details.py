from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("play", "0002_moderation"),
    ]

    operations = [
        migrations.AddField(
            model_name="pratasession",
            name="court_address",
            field=models.CharField(blank=True, max_length=260),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="google_place_id",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="postal_code",
            field=models.CharField(blank=True, max_length=12),
        ),
    ]

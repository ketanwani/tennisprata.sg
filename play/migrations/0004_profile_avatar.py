from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("play", "0003_session_location_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="avatars/"),
        ),
    ]

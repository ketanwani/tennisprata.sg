from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("play", "0011_profile_reminders_by_calendar"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="profile",
            name="avatar_url",
        ),
    ]

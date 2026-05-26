from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("play", "0010_matchresult_losing_player_matchresult_winner_side_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="reminders_by_calendar",
            field=models.BooleanField(default=True),
        ),
    ]

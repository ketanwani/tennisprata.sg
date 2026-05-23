# Generated for the tennisprata.sg POC.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlayGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(unique=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("avatar_url", models.URLField(blank=True)),
                ("ntrp_level", models.CharField(choices=[("beginner", "Beginner"), ("2.5", "2.5"), ("3.0", "3.0"), ("3.5", "3.5"), ("4.0", "4.0"), ("4.5", "4.5+")], default="3.0", max_length=16)),
                ("home_courts", models.CharField(blank=True, max_length=160)),
                ("bio", models.TextField(blank=True)),
                ("reminders_by_email", models.BooleanField(default=True)),
                ("reminders_by_sms", models.BooleanField(default=False)),
                ("reminders_by_whatsapp", models.BooleanField(default=False)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="GroupMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("member", "Member"), ("organizer", "Organizer")], default="member", max_length=16)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="play.playgroup")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("group", "user")}},
        ),
        migrations.AddField(
            model_name="playgroup",
            name="members",
            field=models.ManyToManyField(related_name="play_groups", through="play.GroupMembership", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="Pair",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140)),
                ("is_regular", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pairs", to="play.playgroup")),
                ("players", models.ManyToManyField(blank=True, related_name="pairs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("group", "name")}},
        ),
        migrations.CreateModel(
            name="PrataSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=140)),
                ("starts_at", models.DateTimeField()),
                ("locality", models.CharField(max_length=80)),
                ("court_name", models.CharField(max_length=160)),
                ("court_details", models.CharField(blank=True, max_length=220)),
                ("cost_notes", models.CharField(blank=True, max_length=160)),
                ("level_min", models.CharField(choices=[("beginner", "Beginner"), ("2.5", "2.5"), ("3.0", "3.0"), ("3.5", "3.5"), ("4.0", "4.0"), ("4.5", "4.5+")], default="2.5", max_length=16)),
                ("level_max", models.CharField(choices=[("beginner", "Beginner"), ("2.5", "2.5"), ("3.0", "3.0"), ("3.5", "3.5"), ("4.0", "4.0"), ("4.5", "4.5+")], default="4.5", max_length=16)),
                ("prata_terms", models.CharField(default="Losing pair buys prata after the match.", max_length=180)),
                ("notes", models.TextField(blank=True)),
                ("invite_code", models.CharField(blank=True, max_length=16, unique=True)),
                ("status", models.CharField(choices=[("open", "Open"), ("confirmed", "Confirmed"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="open", max_length=16)),
                ("weather_summary", models.CharField(blank=True, max_length=120)),
                ("weather_risk", models.CharField(default="Pending", max_length=32)),
                ("reminder_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("challenger_pair", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="challenged_sessions", to="play.pair")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to="play.playgroup")),
                ("host", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hosted_sessions", to=settings.AUTH_USER_MODEL)),
                ("host_pair", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="hosted_sessions", to="play.pair")),
            ],
            options={"ordering": ("starts_at",)},
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("is_system", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="play.pratasession")),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.CreateModel(
            name="MatchResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("confirmed_at", models.DateTimeField(auto_now_add=True)),
                ("losing_pair", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lost_results", to="play.pair")),
                ("session", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="result", to="play.pratasession")),
                ("submitted_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("winning_pair", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="won_results", to="play.pair")),
            ],
        ),
        migrations.CreateModel(
            name="ReminderLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS"), ("whatsapp", "WhatsApp"), ("calendar", "Calendar invite")], max_length=16)),
                ("destination", models.CharField(max_length=180)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("provider_message_id", models.CharField(blank=True, max_length=120)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reminder_logs", to="play.pratasession")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SessionParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("side", models.CharField(choices=[("host", "Host"), ("challenger", "Challenger"), ("solo_pool", "Looking for partner")], max_length=24)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("confirmed", "Confirmed")], default="confirmed", max_length=16)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("pair", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="play.pair")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="play.pratasession")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("session", "user")}},
        ),
    ]

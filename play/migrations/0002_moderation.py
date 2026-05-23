from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("play", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pratasession",
            name="cancel_reason",
            field=models.CharField(blank=True, max_length=220),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pratasession",
            name="cancelled_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cancelled_sessions", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="BlockedIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identity_type", models.CharField(choices=[("email", "Email"), ("phone", "Phone")], max_length=16)),
                ("value", models.CharField(max_length=254)),
                ("reason", models.CharField(blank=True, max_length=220)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("identity_type", "value"),
                "unique_together": {("identity_type", "value")},
            },
        ),
    ]

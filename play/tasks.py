from django.utils import timezone

from tennisprata.celery import app

from .models import PrataSession
from .notifications import NotificationPayload, notify_user


@app.task
def send_due_session_reminders():
    sent = 0
    sessions = PrataSession.objects.select_related("host_pair", "challenger_pair").filter(
        status__in=[PrataSession.Status.OPEN, PrataSession.Status.CONFIRMED],
        reminder_sent_at__isnull=True,
        starts_at__gt=timezone.now(),
        starts_at__lte=timezone.now() + timezone.timedelta(hours=24, minutes=15),
    )
    for session in sessions:
        users = {participant.user for participant in session.participants.select_related("user", "user__profile")}
        for user in users:
            sent += send_session_reminder(session.id, user.id)
        session.reminder_sent_at = timezone.now()
        session.save(update_fields=["reminder_sent_at"])
    return sent


@app.task
def send_session_reminder(session_id, user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    session = PrataSession.objects.get(pk=session_id)
    user = User.objects.select_related("profile").get(pk=user_id)
    starts_at = timezone.localtime(session.starts_at)
    subject = f"Reminder: {session.title} starts tomorrow"
    body = (
        f"{session.title}\n"
        f"When: {starts_at:%a, %d %b %Y, %I:%M %p} SGT\n"
        f"Where: {session.court_name} {session.court_details}\n"
        f"Weather: {session.weather_risk} - {session.weather_summary}\n"
        f"Prata vibes: {session.prata_terms or 'No prata stakes. Just tennis and pride.'}\n"
    )
    notify_user(
        user,
        NotificationPayload(
            title=subject,
            body=body,
            url=session.get_absolute_url(),
            session=session,
            include_calendar=True,
        ),
    )
    return 1

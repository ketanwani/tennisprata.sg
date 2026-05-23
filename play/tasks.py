from django.core.mail import send_mail
from django.utils import timezone

from tennisprata.celery import app

from .models import PrataSession, Profile, ReminderLog


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
    profile, _ = Profile.objects.get_or_create(user=user)
    subject = f"Reminder: {session.title} starts tomorrow"
    body = (
        f"{session.title}\n"
        f"When: {session.starts_at:%a, %d %b %Y, %I:%M %p}\n"
        f"Where: {session.court_name} {session.court_details}\n"
        f"Weather: {session.weather_risk} - {session.weather_summary}\n"
        f"Prata vibes: {session.prata_terms or 'No prata stakes. Just tennis and pride.'}\n"
    )

    if profile.reminders_by_email and user.email:
        send_mail(subject, body, None, [user.email], fail_silently=True)
        ReminderLog.objects.create(session=session, user=user, channel=ReminderLog.Channel.EMAIL, destination=user.email)

    if profile.reminders_by_sms and profile.phone:
        send_console_provider_message("sms", profile.phone, body)
        ReminderLog.objects.create(session=session, user=user, channel=ReminderLog.Channel.SMS, destination=profile.phone)

    if profile.reminders_by_whatsapp and profile.phone:
        send_console_provider_message("whatsapp", profile.phone, body)
        ReminderLog.objects.create(session=session, user=user, channel=ReminderLog.Channel.WHATSAPP, destination=profile.phone)

    ReminderLog.objects.create(
        session=session,
        user=user,
        channel=ReminderLog.Channel.CALENDAR,
        destination=user.email or profile.phone,
        provider_message_id="calendar-ics-placeholder",
    )
    return 1


def send_console_provider_message(channel, destination, body):
    print(f"[{channel.upper()} reminder to {destination}]\n{body}")

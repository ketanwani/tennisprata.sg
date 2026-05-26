import logging
from dataclasses import dataclass
from html import escape
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.templatetags.static import static
from django.utils import timezone

from .models import Notification, Profile, ReminderLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationPayload:
    title: str
    body: str
    url: str = ""
    session: object | None = None
    include_calendar: bool = False


def notify_user(user, payload, channels=None, raise_on_delivery_error=False):
    profile, _ = Profile.objects.get_or_create(user=user)
    channels = channels or preferred_channels(user, profile)
    channels = [channel for channel in channels if channel in {"email", "calendar"}]
    Notification.objects.create(user=user, title=payload.title, body=payload.body[:260], url=payload.url)

    sent = []
    if "email" in channels and user.email:
        try:
            if send_email_notification(user.email, payload, profile):
                log_delivery(payload, user, ReminderLog.Channel.EMAIL, user.email)
                sent.append("email")
        except Exception:
            logger.exception("Email notification failed for user_id=%s destination=%s", user.pk, user.email)
            if raise_on_delivery_error:
                raise

    if payload.include_calendar and "calendar" in channels and user.email:
        try:
            if send_calendar_invite(user.email, payload):
                log_delivery(payload, user, ReminderLog.Channel.CALENDAR, user.email, "calendar-ics")
                sent.append("calendar")
        except Exception:
            logger.exception("Calendar invite failed for user_id=%s destination=%s", user.pk, user.email)
            if raise_on_delivery_error:
                raise

    return sent


def preferred_channels(user, profile=None):
    profile = profile or Profile.objects.get(user=user)
    channels = []
    if profile.reminders_by_email:
        channels.append("email")
    if profile.reminders_by_calendar:
        channels.append("calendar")
    return channels


def send_email_notification(destination, payload, profile):
    message = EmailMultiAlternatives(
        subject=payload.title,
        body=payload.body,
        to=[destination],
    )
    message.attach_alternative(render_email_html(payload), "text/html")
    return message.send(fail_silently=False)


def render_email_html(payload):
    logo_url = absolute_url(static("play/email-logo.png"))
    action_url = absolute_url(payload.url) if payload.url else ""
    body_html = "".join(f"<p>{escape(line)}</p>" for line in payload.body.splitlines() if line.strip())
    session_html = render_session_email_card(payload.session) if payload.session else ""
    cta_html = (
        f"""
        <tr>
          <td style="padding: 8px 32px 32px;">
            <a href="{escape(action_url)}" style="display:inline-block; background:#0ac2cc; color:#ffffff; text-decoration:none; font-weight:800; border-radius:999px; padding:14px 22px;">
              Open in tennisprata.sg
            </a>
          </td>
        </tr>
        """
        if action_url
        else ""
    )
    return f"""<!doctype html>
<html>
  <body style="margin:0; padding:0; background:#f4f7fb; color:#222f3c; font-family:Lato, Arial, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f7fb; padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px; background:#ffffff; border:1px solid #e7e9ee; border-radius:28px; overflow:hidden;">
            <tr>
              <td style="padding:28px 32px 18px; background:linear-gradient(135deg,#eaffff,#fff7f2);">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="vertical-align:middle;">
                      <img src="{escape(logo_url)}" width="58" height="58" alt="tennisprata.sg" style="display:block; border-radius:16px;">
                    </td>
                    <td style="vertical-align:middle; padding-left:14px;">
                      <div style="font-size:20px; font-weight:900; color:#222f3c;">tennisprata.sg</div>
                      <div style="font-size:13px; color:#66727c;">Tennis first. Prata optional. Bragging rights mandatory.</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:30px 32px 8px;">
                <h1 style="margin:0; font-size:28px; line-height:1.15; color:#222f3c;">{escape(payload.title)}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 18px; color:#49515d; font-size:16px; line-height:1.55;">
                {body_html}
              </td>
            </tr>
            {session_html}
            {cta_html}
            <tr>
              <td style="padding:22px 32px; background:#fbfcff; border-top:1px solid #e7e9ee; color:#66727c; font-size:12px; line-height:1.5;">
                You are receiving this because email notifications are enabled on tennisprata.sg.
                Manage preferences from the Notifications page.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def render_session_email_card(session):
    starts_at = timezone.localtime(session.starts_at)
    maps_url = ""
    if session.latitude and session.longitude:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={session.latitude},{session.longitude}"
    location = session.court_name
    if session.court_address:
        location = f"{location}, {session.court_address}"
    maps_html = (
        f'<a href="{escape(maps_url)}" style="color:#0aa7d6; font-weight:800; text-decoration:none;">Open map</a>'
        if maps_url
        else ""
    )
    return f"""
      <tr>
        <td style="padding:0 32px 24px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e7e9ee; border-radius:20px; background:#fbfcff;">
            <tr>
              <td style="padding:18px 20px;">
                <div style="font-size:12px; text-transform:uppercase; color:#0ac2cc; font-weight:900;">Session details</div>
                <div style="margin-top:8px; font-size:18px; color:#222f3c; font-weight:900;">{escape(session.title)}</div>
                <div style="margin-top:10px; color:#49515d; line-height:1.6;">
                  <strong>When:</strong> {starts_at:%a, %d %b %Y, %I:%M %p} SGT<br>
                  <strong>Where:</strong> {escape(location)} {maps_html}<br>
                  <strong>Weather:</strong> {escape(session.weather_risk)} - {escape(session.weather_summary or "Check closer to match time")}<br>
                  <strong>Prata vibes:</strong> {escape(session.prata_terms or "No prata stakes. Just tennis and pride.")}
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    """


def absolute_url(path):
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(f"{settings.APP_BASE_URL.rstrip('/')}/", path.lstrip("/"))


def send_calendar_invite(destination, payload):
    if not payload.session:
        return 0
    session = payload.session
    starts_at = timezone.localtime(session.starts_at)
    ends_at = starts_at + timezone.timedelta(hours=2)
    uid = f"tennisprata-session-{session.pk}@tennisprata.sg"
    description = payload.body.replace("\n", "\\n")
    ics = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//tennisprata.sg//Session Reminder//EN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{timezone.now().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{starts_at.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{ends_at.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{session.title}",
            f"LOCATION:{session.court_name}",
            f"DESCRIPTION:{description}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )
    message = EmailMultiAlternatives(
        subject=f"Calendar invite: {session.title}",
        body=payload.body,
        to=[destination],
    )
    message.attach("tennisprata-session.ics", ics, "text/calendar")
    return message.send(fail_silently=False)


def log_delivery(payload, user, channel, destination, provider_message_id=""):
    if not payload.session:
        return
    ReminderLog.objects.create(
        session=payload.session,
        user=user,
        channel=channel,
        destination=destination,
        provider_message_id=provider_message_id,
    )

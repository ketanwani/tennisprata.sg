"""
Reusable UX/product audit for tennisprata.sg.

Run from the repo root, preferably inside the Docker web container:

    docker compose exec web python scripts/ux_audit.py

The script creates isolated ux_audit_* records, renders representative pages
with Django's test client, checks product/UX heuristics, writes a Markdown
report to qa-artifacts/ux_audit_report.md, and then cleans up its data.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tennisprata.settings")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django  # noqa: E402

django.setup()

from allauth.account.models import EmailAddress  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.test import Client, override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from play.models import (  # noqa: E402
    GroupMembership,
    MatchResult,
    MatchSetScore,
    Notification,
    Pair,
    PlayGroup,
    PrataSession,
    Profile,
    SessionParticipant,
)


ROOT = Path(__file__).resolve().parents[1]
STATIC_CSS = ROOT / "static" / "play" / "styles.css"
BASE_TEMPLATE = ROOT / "templates" / "base.html"
REPORT_PATH = ROOT / "qa-artifacts" / "ux_audit_report.md"


@dataclass
class Finding:
    area: str
    severity: str
    title: str
    evidence: str
    recommendation: str


@dataclass
class Check:
    area: str
    name: str
    passed: bool
    evidence: str = ""


checks: list[Check] = []
findings: list[Finding] = []


def add_check(area: str, name: str, passed: bool, evidence: str = ""):
    checks.append(Check(area, name, bool(passed), evidence))


def add_finding(area: str, severity: str, title: str, evidence: str, recommendation: str):
    findings.append(Finding(area, severity, title, evidence, recommendation))


def html_text(html: bytes | str) -> str:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def count(html: bytes | str, needle: str) -> int:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    return html.count(needle)


def contains_all(html: bytes | str, needles: list[str]) -> bool:
    text = html_text(html)
    return all(needle in text for needle in needles)


def make_user(username: str, email: str, *, staff: bool = False) -> User:
    user = User.objects.create_user(
        username=username,
        email=email,
        password="StrongPass12345!",
        first_name=username.replace("ux_audit_", "").title(),
    )
    user.is_staff = staff
    user.is_superuser = staff
    user.save(update_fields=["is_staff", "is_superuser"])
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    Profile.objects.update_or_create(
        user=user,
        defaults={"ntrp_level": "3.5", "home_courts": "Kallang", "bio": "UX audit account"},
    )
    return user


def reset_data():
    PrataSession.objects.filter(title__startswith="UX Audit").delete()
    Pair.objects.filter(name__startswith="UX Audit").delete()
    Notification.objects.filter(user__email__startswith="ux_audit_").delete()
    User.objects.filter(email__startswith="ux_audit_").delete()


def login_client(user: User) -> Client:
    client = Client()
    if not client.login(username=user.username, password="StrongPass12345!"):
        raise RuntimeError(f"Could not login UX audit user {user.username}")
    return client


def setup_fixture():
    group, _ = PlayGroup.objects.get_or_create(
        slug="kallang-sunday-tennis",
        defaults={"name": "Kallang Sunday Tennis", "description": "UX audit group"},
    )
    host = make_user("ux_audit_host", "ux_audit_host@example.com")
    host_partner = make_user("ux_audit_host_partner", "ux_audit_host_partner@example.com")
    challenger = make_user("ux_audit_challenger", "ux_audit_challenger@example.com")
    challenger_partner = make_user("ux_audit_challenger_partner", "ux_audit_challenger_partner@example.com")
    staff = make_user("ux_audit_staff", "ux_audit_staff@example.com", staff=True)

    for user in [host, host_partner, challenger, challenger_partner, staff]:
        GroupMembership.objects.get_or_create(group=group, user=user)

    host_pair = Pair.objects.create(group=group, name="UX Audit Host Pair", status=Pair.Status.CONFIRMED, is_regular=True)
    host_pair.players.add(host, host_partner)
    challenger_pair = Pair.objects.create(
        group=group,
        name="UX Audit Challenger Pair",
        status=Pair.Status.CONFIRMED,
        is_regular=True,
    )
    challenger_pair.players.add(challenger, challenger_partner)
    pending_pair = Pair.objects.create(
        group=group,
        name="UX Audit Pending Pair",
        status=Pair.Status.PENDING,
        is_regular=True,
        invited_email="ux_audit_challenger@example.com",
    )
    pending_pair.players.add(host)

    future = PrataSession.objects.create(
        group=group,
        title="UX Audit Future Doubles",
        match_type=PrataSession.MatchType.DOUBLES,
        host=host,
        host_pair=host_pair,
        challenger_pair=challenger_pair,
        starts_at=timezone.now() + timedelta(days=3),
        court_name="Kallang Tennis Centre",
        court_address="52 Stadium Road",
        postal_code="397724",
        locality="Kallang",
        latitude="1.302300",
        longitude="103.876900",
        status=PrataSession.Status.CONFIRMED,
        weather_summary="Audit clear sky",
        weather_risk="Low",
    )
    SessionParticipant.objects.create(session=future, user=host, pair=host_pair, side=SessionParticipant.Side.HOST)
    SessionParticipant.objects.create(
        session=future,
        user=challenger,
        pair=challenger_pair,
        side=SessionParticipant.Side.CHALLENGER,
    )

    completed = PrataSession.objects.create(
        group=group,
        title="UX Audit Completed Singles",
        match_type=PrataSession.MatchType.SINGLES,
        host=host,
        challenger_player=challenger,
        starts_at=timezone.now() - timedelta(hours=2),
        court_name="Kallang Tennis Centre",
        locality="Kallang",
        status=PrataSession.Status.COMPLETED,
        weather_summary="Audit clear sky",
        weather_risk="Low",
    )
    SessionParticipant.objects.create(session=completed, user=host, side=SessionParticipant.Side.HOST)
    SessionParticipant.objects.create(session=completed, user=challenger, side=SessionParticipant.Side.CHALLENGER)
    result = MatchResult.objects.create(
        session=completed,
        winner_side=MatchResult.WinnerSide.HOST,
        winning_player=host,
        losing_player=challenger,
        submitted_by=host,
    )
    MatchSetScore.objects.create(result=result, set_number=1, host_score=6, challenger_score=4)
    MatchSetScore.objects.create(result=result, set_number=2, host_score=6, challenger_score=3)

    Notification.objects.create(
        user=host,
        title="UX Audit notification",
        body="This is a notification preview for the profile panel.",
        url=future.get_absolute_url(),
    )

    return {
        "host": host,
        "staff": staff,
        "challenger": challenger,
        "future": future,
        "completed": completed,
        "pending_pair": pending_pair,
    }


def audit_static_foundation():
    css = STATIC_CSS.read_text(encoding="utf-8")
    base = BASE_TEMPLATE.read_text(encoding="utf-8")

    add_check("Responsive foundation", "Viewport meta tag is present", 'name="viewport"' in base)
    add_check("Responsive foundation", "Tablet/mobile breakpoint exists at 980px", "@media (max-width: 980px)" in css)
    add_check("Responsive foundation", "Phone breakpoint exists at 760px", "@media (max-width: 760px)" in css)
    add_check("Responsive foundation", "Session cards stack on smaller screens", ".session-card" in css and "flex-direction: column" in css)
    add_check("Responsive foundation", "Chat form becomes one column on mobile", ".chat-form" in css and "grid-template-columns: 1fr" in css)
    add_check("Responsive foundation", "Main join CTA is fixed near thumb zone on mobile", ".session-primary-action" in css and "position: fixed" in css)

    logged_in_nav = re.search(r"{% if user\.is_authenticated %}([\s\S]*?){% else %}", base)
    nav_links = re.findall(r"<a ", logged_in_nav.group(1)) if logged_in_nav else []
    has_secondary_menu = 'class="nav-more"' in base and 'class="nav-more-menu"' in base
    add_check("Navigation", "Logged-in navigation is discoverable", bool(logged_in_nav), f"{len(nav_links)} links")
    add_check("Navigation", "Secondary logged-in links are grouped", has_secondary_menu)
    if len(nav_links) >= 7 and not has_secondary_menu:
        add_finding(
            "Navigation",
            "Medium",
            "Logged-in mobile navigation is likely dense",
            f"The authenticated header has {len(nav_links)} links plus Logout in a wrapped pill nav.",
            "Consider a compact mobile menu or grouping secondary items like Notifications, Feedback, and Moderation.",
        )

    danger_is_distinct = (
        "--danger:" in css
        and re.search(r"\.danger\s*{[^}]*background:\s*var\(--danger\)", css)
        and not re.search(r"\.danger\s*{[^}]*background:\s*var\(--clay\)", css)
    )
    add_check("Actions", "Destructive actions use a distinct danger style", danger_is_distinct)
    if not danger_is_distinct:
        add_finding(
            "Actions",
            "Medium",
            "Destructive actions look too similar to primary actions",
            "The `.danger` button uses the same teal/clay token as primary buttons.",
            "Use a distinct red/critical style for Cancel, Delete, Withdraw, and Disable actions.",
        )


def audit_page(client: Client, name: str, url: str, expected: list[str], *, min_buttons: int = 0):
    response = client.get(url)
    html = response.content
    add_check(name, "Page returns 200", response.status_code == 200, f"status={response.status_code}")
    add_check(name, "Has page heading", b"<h1" in html)
    add_check(name, "Expected product copy appears", contains_all(html, expected), ", ".join(expected))
    if min_buttons:
        add_check(name, "Primary actions are present", count(html, 'class="button') + count(html, "<button") >= min_buttons)
    return response


def audit_pages(data):
    host_client = login_client(data["host"])
    staff_client = login_client(data["staff"])
    challenger_client = login_client(data["challenger"])
    anon = Client()

    landing = audit_page(
        anon,
        "Landing",
        "/",
        ["prata", "tennis", "challenge"],
        min_buttons=1,
    )
    add_check("Landing", "Logged-out landing does not leak session list", "Upcoming prata sessions" not in html_text(landing.content))

    signup = audit_page(anon, "Signup", "/signup/", ["Create profile", "verification link"], min_buttons=1)
    add_check("Signup", "Phone signup field is removed", "Phone number" not in html_text(signup.content))
    add_check("Signup", "NTRP slider enhancement hook exists", b'data-ntrp-slider="true"' in signup.content)

    login = audit_page(anon, "Login", "/login/", ["Login", "verified email address"], min_buttons=1)
    add_check("Login", "Login no longer mentions phone", "phone number" not in html_text(login.content).lower())

    dashboard = audit_page(
        host_client,
        "Dashboard",
        "/",
        ["Prata dashboard", "UX Audit Future Doubles", "Leaderboard"],
        min_buttons=2,
    )
    add_check("Dashboard", "Metric cards have consistent class", count(dashboard.content, "dashboard-stat-card") == 4)
    add_check("Dashboard", "Pair invite metric is clickable and labelled", b'aria-label="View pair invites"' in dashboard.content)
    add_check("Dashboard", "Dashboard no longer embeds full leaderboard list", "Pair leaderboard" not in html_text(dashboard.content))

    my_sessions = audit_page(
        host_client,
        "My Sessions",
        "/my-sessions/",
        ["My sessions", "Needs result", "Upcoming", "Completed", "Cancelled"],
    )
    add_check("My Sessions", "Post-match flow is visible from history", b"UX Audit Completed Singles" in my_sessions.content)

    leaderboard = audit_page(host_client, "Leaderboard", "/leaderboard/", ["Leaderboard", "Singles", "Doubles"])
    add_check("Leaderboard", "Dedicated leaderboard page avoids dashboard overflow", b"leaderboard-page" in leaderboard.content)

    profile = audit_page(host_client, "Profile", "/profile/", ["Profile", "UX Audit Host Pair", "Pair invites"])
    add_check("Profile", "Avatar URL field is gone", "avatar_url" not in profile.content.decode("utf-8", errors="ignore"))

    notifications = audit_page(
        host_client,
        "Notifications",
        "/notifications/preferences/",
        ["Notifications", "Email", "SMS", "Upcoming feature"],
    )
    add_check("Notifications", "Upcoming SMS and WhatsApp are visibly disabled", b"disabled" in notifications.content)

    create_session = audit_page(
        host_client,
        "Create Challenge",
        "/sessions/new/",
        ["Create prata challenge", "Play location", "Prata vibes", "NTRP"],
        min_buttons=1,
    )
    add_check("Create Challenge", "Date field prevents obvious past-date selection", b'type="date"' in create_session.content and b"min=" in create_session.content)
    add_check("Create Challenge", "Locality/address coordinate fields stay hidden", b'hidden-location-fields' in create_session.content)
    add_check("Create Challenge", "Prata terms are non-editable", b"readonly" in create_session.content)

    session_detail = audit_page(
        host_client,
        "Session Detail",
        data["future"].get_absolute_url(),
        ["UX Audit Future Doubles", "Kallang Tennis Centre", "Low", "Session chat"],
        min_buttons=2,
    )
    add_check("Session Detail", "Exactly one copy invite control is present", count(session_detail.content, "data-copy-url=") == 1)
    add_check("Session Detail", "Static map preview is present", b"map-preview" in session_detail.content)
    add_check("Session Detail", "Team pairing is visible", b"Host pair" in session_detail.content and b"Challenger pair" in session_detail.content)

    completed_detail = audit_page(
        host_client,
        "Completed Session",
        data["completed"].get_absolute_url(),
        ["UX Audit Completed Singles", "6-4", "Post-match shoutouts"],
    )
    add_check("Completed Session", "Badge-style shoutout UI is present", b"badge-choice-grid" in completed_detail.content)

    pair_invite = audit_page(
        challenger_client,
        "Pair Invite",
        data["pending_pair"].accept_url,
        ["Join", "Accept this invite", "Accept pair invite"],
        min_buttons=1,
    )
    add_check("Pair Invite", "Invite acceptance is explicit", b"Accept pair invite" in pair_invite.content)

    moderation = audit_page(staff_client, "Moderation", "/moderation/", ["Moderation", "Block email"])
    add_check("Moderation", "Moderation copy focuses on email block, not phone auth", "phone numbers" not in html_text(moderation.content))


def write_report():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for check in checks if check.passed)
    failed = len(checks) - passed
    by_severity = {severity: sum(1 for item in findings if item.severity == severity) for severity in ["High", "Medium", "Low"]}

    lines = [
        "# tennisprata.sg UX Audit",
        "",
        f"Generated: {timezone.localtime():%Y-%m-%d %H:%M:%S %Z}",
        "",
        "## Summary",
        "",
        f"- Heuristic checks passed: {passed}/{len(checks)}",
        f"- Heuristic checks failed: {failed}",
        f"- Findings: {len(findings)} ({by_severity['High']} high, {by_severity['Medium']} medium, {by_severity['Low']} low)",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.extend(
                [
                    f"### [{item.severity}] {item.title}",
                    "",
                    f"- Area: {item.area}",
                    f"- Evidence: {item.evidence}",
                    f"- Recommendation: {item.recommendation}",
                    "",
                ]
            )
    else:
        lines.append("No UX findings were detected by this audit.")
        lines.append("")

    lines.extend(["## Check Results", ""])
    for check in checks:
        mark = "PASS" if check.passed else "FAIL"
        evidence = f" - {check.evidence}" if check.evidence else ""
        lines.append(f"- {mark}: {check.area} - {check.name}{evidence}")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT_PATH


def main():
    settings = override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
    settings.enable()
    try:
        reset_data()
        data = setup_fixture()
        audit_static_foundation()
        audit_pages(data)
        report = write_report()
    finally:
        reset_data()
        settings.disable()

    print(f"UX audit checks: {sum(1 for c in checks if c.passed)}/{len(checks)} passed")
    print(f"UX findings: {len(findings)}")
    for finding in findings:
        print(f"- [{finding.severity}] {finding.title}")
    print(f"Report written to {report}")
    if any(not check.passed for check in checks):
        sys.exit(1)


if __name__ == "__main__":
    main()

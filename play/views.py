from allauth.account.utils import send_email_confirmation
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import LoginView, LogoutView
from django.core.cache import cache
from django.db.models import Avg, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from collections import Counter
import json
import os
import math
import secrets
import urllib.parse
import urllib.request

from .forms import (
    BlockedIdentityForm,
    CancelSessionForm,
    ChatMessageForm,
    ContactLoginForm,
    DisableUserForm,
    JoinSessionForm,
    MatchScoreForm,
    NotificationPreferencesForm,
    PairInviteForm,
    PairForm,
    PrataSessionForm,
    ProfileForm,
    SessionSearchForm,
    SignupForm,
    TestimonialForm,
)
from .identity import create_unverified_primary_email, email_address_is_verified
from .models import (
    BlockedIdentity,
    ChatMessage,
    GroupMembership,
    MatchResult,
    MatchSetScore,
    Notification,
    Pair,
    PlayGroup,
    PrataSession,
    Profile,
    ReminderLog,
    SessionParticipant,
    TESTIMONIAL_BADGE_CHOICES,
    Testimonial,
    normalize_identity,
)
from .notifications import NotificationPayload, notify_user
from .weather import weather_risk_for


def add_form_error_messages(request, form, fallback="Please fix the highlighted fields."):
    errors = []
    for field_name, field_errors in form.errors.items():
        label = form.fields.get(field_name).label if field_name in form.fields else "Form"
        for error in field_errors:
            errors.append(f"{label}: {error}")
    messages.error(request, errors[0] if errors else fallback)


def create_notification(user, title, body, url=""):
    Notification.objects.create(user=user, title=title, body=body, url=url)


def user_can_cancel_session(user, session):
    if not user.is_authenticated:
        return False
    if session.is_singles:
        return session.host_id == user.id
    return bool(session.host_pair and session.host_pair.players.filter(pk=user.pk).exists())


def user_can_join_session(user, session, result=None):
    if not user.is_authenticated:
        return False
    if result or session.status != PrataSession.Status.OPEN:
        return False
    if session.host_id == user.id:
        return False
    if session.is_singles:
        return session.challenger_player_id is None
    if session.host_pair and session.host_pair.players.filter(pk=user.pk).exists():
        return False
    return session.challenger_pair_id is None


def user_can_access_session_chat(user, session):
    if not user.is_authenticated:
        return False
    if user.is_staff or session.host_id == user.id:
        return True
    if session.is_singles and session.challenger_player_id == user.id:
        return True
    if session.host_pair and session.host_pair.players.filter(pk=user.pk).exists():
        return True
    if session.challenger_pair and session.challenger_pair.players.filter(pk=user.pk).exists():
        return True
    return session.participants.filter(user=user).exists()


def user_can_view_session_detail(user, session):
    if not user.is_authenticated:
        return False
    if user.is_staff or session.host_id == user.id:
        return True
    if session.is_singles and session.challenger_player_id == user.id:
        return True
    if session.host_pair and session.host_pair.players.filter(pk=user.pk).exists():
        return True
    if session.challenger_pair and session.challenger_pair.players.filter(pk=user.pk).exists():
        return True
    return session.participants.filter(user=user).exists()


def user_can_access_post_match(user, session):
    if not user.is_authenticated:
        return False
    if user.is_staff or session.host_id == user.id:
        return True
    if session.host_pair and session.host_pair.players.filter(pk=user.pk).exists():
        return True
    if session.challenger_pair and session.challenger_pair.players.filter(pk=user.pk).exists():
        return True
    if session.challenger_player_id == user.id:
        return True
    return session.participants.filter(user=user).exists()


def session_has_started(session):
    return timezone.now() >= session.starts_at


def user_can_submit_post_match(user, session):
    return user.is_authenticated and user_can_access_post_match(user, session)


def session_has_challenger(session):
    return bool(session.challenger_player_id or session.challenger_pair_id)


def session_player_users(session):
    players = []

    def add(user):
        if user and all(existing.pk != user.pk for existing in players):
            players.append(user)

    if session.is_singles:
        add(session.host)
        add(session.challenger_player)
    else:
        if session.host_pair_id:
            for player in session.host_pair.players.select_related("profile").all():
                add(player)
        if session.challenger_pair_id:
            for player in session.challenger_pair.players.select_related("profile").all():
                add(player)
    for participant in session.participants.select_related("user", "user__profile"):
        add(participant.user)
    return players


def session_match_sides(session):
    def player_item(user):
        return {"user": user, "name": user.get_full_name() or user.username} if user else None

    if session.is_singles:
        host_players = [player_item(session.host)]
        challenger_players = [player_item(session.challenger_player)] if session.challenger_player else []
    else:
        host_players = [
            player_item(player)
            for player in (session.host_pair.players.select_related("profile").all() if session.host_pair_id else [])
        ]
        challenger_players = [
            player_item(player)
            for player in (
                session.challenger_pair.players.select_related("profile").all() if session.challenger_pair_id else []
            )
        ]

    return [
        {
            "label": "Host side" if session.is_singles else "Host pair",
            "name": session.host_side_name,
            "players": [player for player in host_players if player],
            "is_open": False,
        },
        {
            "label": "Challenger side" if session.is_singles else "Challenger pair",
            "name": session.challenger_side_name,
            "players": [player for player in challenger_players if player],
            "is_open": not session_has_challenger(session),
        },
    ]


def notify_host_side_session_joined(session, joined_name, actor=None):
    recipients = []

    def add_recipient(user):
        if user and user != actor and all(existing.pk != user.pk for existing in recipients):
            recipients.append(user)

    add_recipient(session.host)
    if session.host_pair_id:
        for player in session.host_pair.players.all():
            add_recipient(player)

    starts_at = timezone.localtime(session.starts_at)
    for user in recipients:
        notify_user(
            user,
            NotificationPayload(
                title=f"{joined_name} joined your prata challenge",
                body=(
                    f"{joined_name} joined {session.title}.\n"
                    f"When: {starts_at:%a, %d %b %Y, %I:%M %p} SGT\n"
                    f"Where: {session.court_name}"
                ),
                url=session.get_absolute_url(),
                session=session,
            ),
        )


def apply_score_result(session, user, form):
    winner_side = form.cleaned_data["winner_side"]
    result_defaults = {
        "winner_side": winner_side,
        "submitted_by": user,
        "winning_pair": None,
        "losing_pair": None,
        "winning_player": None,
        "losing_player": None,
    }
    if session.is_singles:
        result_defaults["winning_player"] = session.host if winner_side == MatchResult.WinnerSide.HOST else session.challenger_player
        result_defaults["losing_player"] = session.challenger_player if winner_side == MatchResult.WinnerSide.HOST else session.host
    else:
        result_defaults["winning_pair"] = session.host_pair if winner_side == MatchResult.WinnerSide.HOST else session.challenger_pair
        result_defaults["losing_pair"] = session.challenger_pair if winner_side == MatchResult.WinnerSide.HOST else session.host_pair

    result, _ = MatchResult.objects.update_or_create(session=session, defaults=result_defaults)
    result.set_scores.all().delete()
    MatchSetScore.objects.bulk_create(
        [
            MatchSetScore(
                result=result,
                set_number=set_number,
                host_score=host_score,
                challenger_score=challenger_score,
            )
            for set_number, host_score, challenger_score in form.cleaned_data["sets"]
        ]
    )
    session.status = PrataSession.Status.COMPLETED
    session.save(update_fields=["status"])
    return result


def distance_km(lat1, lng1, lat2, lng2):
    radius = 6371
    lat1, lng1, lat2, lng2 = map(math.radians, [float(lat1), float(lng1), float(lat2), float(lng2)])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def player_name(user):
    return user.get_full_name() or user.username


def player_match_stats(user, group=None):
    singles_wins = MatchResult.objects.filter(winning_player=user)
    singles_losses = MatchResult.objects.filter(losing_player=user)
    doubles_wins = MatchResult.objects.filter(winning_pair__players=user)
    doubles_losses = MatchResult.objects.filter(losing_pair__players=user)
    if group:
        singles_wins = singles_wins.filter(session__group=group)
        singles_losses = singles_losses.filter(session__group=group)
        doubles_wins = doubles_wins.filter(session__group=group)
        doubles_losses = doubles_losses.filter(session__group=group)
    return {
        "singles_wins": singles_wins.count(),
        "singles_losses": singles_losses.count(),
        "doubles_wins": doubles_wins.count(),
        "doubles_losses": doubles_losses.count(),
    }


def leaderboard_points(wins, losses):
    return wins * 3 + losses


def build_player_leaderboard(group):
    ranked = []
    users = User.objects.filter(play_groups=group, is_active=True).select_related("profile").distinct()
    for user in users:
        stats = player_match_stats(user, group)
        wins = stats["singles_wins"] + stats["doubles_wins"]
        losses = stats["singles_losses"] + stats["doubles_losses"]
        if wins or losses:
            ranked.append(
                {
                    "user": user,
                    "name": player_name(user),
                    "wins": wins,
                    "losses": losses,
                    "points": leaderboard_points(wins, losses),
                    "singles": f'{stats["singles_wins"]}W {stats["singles_losses"]}L',
                    "doubles": f'{stats["doubles_wins"]}W {stats["doubles_losses"]}L',
                }
            )
    return sorted(ranked, key=lambda item: (item["points"], item["wins"], item["name"].lower()), reverse=True)


def build_singles_leaderboard(group):
    ranked = []
    users = User.objects.filter(play_groups=group, is_active=True).select_related("profile").distinct()
    for user in users:
        stats = player_match_stats(user, group)
        wins = stats["singles_wins"]
        losses = stats["singles_losses"]
        if wins or losses:
            ranked.append(
                {
                    "user": user,
                    "name": player_name(user),
                    "wins": wins,
                    "losses": losses,
                    "points": leaderboard_points(wins, losses),
                }
            )
    return sorted(ranked, key=lambda item: (item["points"], item["wins"], item["name"].lower()), reverse=True)


def build_pair_leaderboard(group):
    ranked = []
    pairs = group.pairs.filter(status=Pair.Status.CONFIRMED).prefetch_related("players")
    for pair in pairs:
        wins = pair.wins
        losses = pair.losses
        if wins or losses:
            ranked.append(pair)
    return sorted(ranked, key=lambda pair: (pair.points, pair.wins, pair.name.lower()), reverse=True)


def testimonial_summary(user):
    received = Testimonial.objects.filter(reviewed_user=user).select_related("reviewer", "session")[:8]
    average = Testimonial.objects.filter(reviewed_user=user).aggregate(avg=Avg("rating"))["avg"]
    badge_counter = Counter()
    for testimonial in Testimonial.objects.filter(reviewed_user=user):
        badge_counter.update(testimonial.badges)
    labels = dict(TESTIMONIAL_BADGE_CHOICES)
    return {
        "average": average,
        "count": Testimonial.objects.filter(reviewed_user=user).count(),
        "recent": received,
        "top_badges": [(labels.get(key, key), count) for key, count in badge_counter.most_common(4)],
    }


def pending_pair_invites_for(user):
    query = Q()
    if user.email and email_address_is_verified(user):
        query |= Q(invited_email__iexact=user.email)
    if not query:
        return Pair.objects.none()
    return (
        Pair.objects.select_related("group")
        .prefetch_related("players__profile")
        .filter(query, status=Pair.Status.PENDING)
        .exclude(players=user)
        .order_by("-created_at")
    )


def rate_limit_key(request, scope):
    if request.user.is_authenticated:
        return f"rate:{scope}:user:{request.user.pk}"
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded_for.split(",", 1)[0].strip() or request.META.get("REMOTE_ADDR", "unknown")
    return f"rate:{scope}:ip:{ip}"


def is_rate_limited(request, scope, limit, window_seconds):
    key = rate_limit_key(request, scope)
    count = cache.get(key, 0)
    if count >= limit:
        return True
    if count:
        cache.incr(key)
    else:
        cache.set(key, 1, window_seconds)
    return False


def sessions_for_user(user):
    return (
        PrataSession.objects.select_related("host", "host_pair", "challenger_pair", "challenger_player", "result")
        .filter(
            Q(participants__user=user)
            | Q(host=user)
            | Q(challenger_player=user)
            | Q(host_pair__players=user)
            | Q(challenger_pair__players=user)
        )
        .distinct()
        .order_by("-starts_at")
    )


def session_workflow_items(user):
    now = timezone.now()
    upcoming = []
    needs_result = []
    completed = []
    cancelled = []
    for session in sessions_for_user(user):
        result = getattr(session, "result", None)
        players = session_player_users(session)
        shoutouts_remaining = 0
        if result and user in players:
            reviewed_user_ids = set(
                Testimonial.objects.filter(session=session, reviewer=user).values_list("reviewed_user_id", flat=True)
            )
            shoutouts_remaining = sum(1 for player in players if player != user and player.id not in reviewed_user_ids)
        item = {
            "session": session,
            "has_started": session.starts_at <= now,
            "has_result": bool(result),
            "can_record_score": session.starts_at <= now
            and not result
            and session_has_challenger(session)
            and user_can_submit_post_match(user, session),
            "can_give_shoutouts": bool(shoutouts_remaining),
            "shoutouts_remaining": shoutouts_remaining,
        }
        if session.status == PrataSession.Status.CANCELLED:
            cancelled.append(item)
        elif item["can_record_score"]:
            needs_result.append(item)
        elif session.starts_at >= now:
            upcoming.append(item)
        elif result or session.status == PrataSession.Status.COMPLETED:
            completed.append(item)
        else:
            needs_result.append(item)
    return {
        "upcoming": upcoming,
        "needs_result": needs_result,
        "completed": completed,
        "cancelled": cancelled,
    }


def ensure_demo_group(user=None):
    group, _ = PlayGroup.objects.get_or_create(
        slug="kallang-sunday-tennis",
        defaults={
            "name": "Kallang Sunday Tennis",
            "description": "POC group for prata doubles challenges.",
        },
    )
    if user and user.is_authenticated:
        GroupMembership.objects.get_or_create(group=group, user=user)
    return group


def dashboard(request):
    if not request.user.is_authenticated:
        return render(request, "play/landing.html")

    group = ensure_demo_group(request.user)
    upcoming = sessions_for_user(request.user).filter(starts_at__gte=timezone.now()).order_by("starts_at")[:8]
    leaderboard = build_pair_leaderboard(group)
    singles_leaderboard = build_singles_leaderboard(group)
    pair_invites = pending_pair_invites_for(request.user)
    return render(
        request,
        "play/dashboard.html",
        {
            "group": group,
            "upcoming": upcoming,
            "leaderboard": leaderboard,
            "leaderboard_total": len(leaderboard),
            "singles_leaderboard_total": len(singles_leaderboard),
            "pair_invites_count": pair_invites.count(),
        },
    )


@login_required
def leaderboard(request):
    group = ensure_demo_group(request.user)
    pair_leaderboard = build_pair_leaderboard(group)
    singles_leaderboard = build_singles_leaderboard(group)
    return render(
        request,
        "play/leaderboard.html",
        {
            "pair_leaderboard": pair_leaderboard,
            "singles_leaderboard": singles_leaderboard,
            "pair_count": len(pair_leaderboard),
            "singles_count": len(singles_leaderboard),
        },
    )


@login_required
def my_sessions(request):
    buckets = session_workflow_items(request.user)
    return render(
        request,
        "play/my_sessions.html",
        {
            "upcoming_items": buckets["upcoming"],
            "needs_result_items": buckets["needs_result"],
            "completed_items": buckets["completed"],
            "cancelled_items": buckets["cancelled"],
        },
    )


@login_required
def session_search(request):
    group = ensure_demo_group(request.user)
    form = SessionSearchForm(request.GET or None)
    sessions = group.sessions.select_related(
        "host",
        "host_pair",
        "challenger_pair",
        "challenger_player",
    ).order_by("starts_at")
    location_radius_used = False

    if form.is_valid():
        location = form.cleaned_data.get("location", "").strip()
        latitude = form.cleaned_data.get("latitude")
        longitude = form.cleaned_data.get("longitude")
        radius_km = form.cleaned_data.get("radius_km")
        if location and not (latitude and longitude and radius_km):
            sessions = sessions.filter(
                Q(court_name__icontains=location)
                | Q(locality__icontains=location)
                | Q(court_address__icontains=location)
                | Q(postal_code__icontains=location)
            )
        host = form.cleaned_data.get("host", "").strip()
        if host:
            sessions = sessions.filter(
                Q(host__first_name__icontains=host)
                | Q(host__last_name__icontains=host)
                | Q(host__username__icontains=host)
                | Q(host_pair__name__icontains=host)
            )
        if form.cleaned_data.get("match_type"):
            sessions = sessions.filter(match_type=form.cleaned_data["match_type"])
        if form.cleaned_data.get("status"):
            sessions = sessions.filter(status=form.cleaned_data["status"])
        if form.cleaned_data.get("date_from"):
            start = timezone.make_aware(
                timezone.datetime.combine(form.cleaned_data["date_from"], timezone.datetime.min.time()),
                timezone.get_current_timezone(),
            )
            sessions = sessions.filter(starts_at__gte=start)
        if form.cleaned_data.get("date_to"):
            end = timezone.make_aware(
                timezone.datetime.combine(form.cleaned_data["date_to"], timezone.datetime.max.time()),
                timezone.get_current_timezone(),
            )
            sessions = sessions.filter(starts_at__lte=end)
        if form.cleaned_data.get("time_from"):
            sessions = [session for session in sessions if timezone.localtime(session.starts_at).time() >= form.cleaned_data["time_from"]]
        if form.cleaned_data.get("time_to"):
            sessions = [session for session in sessions if timezone.localtime(session.starts_at).time() <= form.cleaned_data["time_to"]]
        if latitude and longitude and radius_km:
            location_radius_used = True
            sessions = [
                session
                for session in sessions
                if session.latitude
                and session.longitude
                and distance_km(latitude, longitude, session.latitude, session.longitude) <= float(radius_km)
            ]
    elif request.GET:
        add_form_error_messages(request, form, "Search filters could not be applied.")

    return render(
        request,
        "play/session_search.html",
        {
            "form": form,
            "sessions": sessions[:80] if hasattr(sessions, "__getitem__") else sessions,
            "location_radius_used": location_radius_used,
        },
    )


@login_required
def location_search(request):
    if is_rate_limited(request, "location-search", limit=30, window_seconds=60):
        return JsonResponse({"results": [], "error": "Too many location searches. Please slow down."}, status=429)
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    normalized_query = " ".join(query.lower().split())
    cache_key = f"onemap:search:{normalized_query}"
    cached_results = cache.get(cache_key)
    if cached_results is not None:
        return JsonResponse({"results": cached_results, "cache_status": "hit"})

    results = search_onemap(query)[:8]
    ttl = 7 * 24 * 60 * 60 if results else 10 * 60
    cache.set(cache_key, results, ttl)
    return JsonResponse({"results": results, "cache_status": "miss"})


def search_onemap(query):
    params = urllib.parse.urlencode({"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
    url = f"https://www.onemap.gov.sg/api/common/elastic/search?{params}"
    headers = {}
    token = os.getenv("ONEMAP_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = token
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if payload.get("error"):
        return []

    results = []
    for item in payload.get("results", []):
        name = item.get("BUILDING") if item.get("BUILDING") != "NIL" else item.get("SEARCHVAL", "")
        address_parts = [item.get("BLK_NO", ""), item.get("ROAD_NAME", "")]
        address = " ".join(part for part in address_parts if part and part != "NIL").strip()
        postal = item.get("POSTAL", "")
        results.append(
            {
                "name": name or item.get("SEARCHVAL", ""),
                "address": address or item.get("ADDRESS", ""),
                "locality": one_map_locality(item),
                "postal_code": postal if postal != "NIL" else "",
                "latitude": item.get("LATITUDE", ""),
                "longitude": item.get("LONGITUDE", ""),
                "source": "OneMap",
            }
        )
    return results


def one_map_locality(item):
    for value in (item.get("ROAD_NAME", ""), item.get("ADDRESS", ""), item.get("SEARCHVAL", "")):
        if value and value != "NIL":
            parts = value.replace(",", " ").split()
            return " ".join(parts[:2])[:80]
    return ""


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            ensure_demo_group(user)
            create_unverified_primary_email(user)
            sent = send_email_confirmation(request, user, signup=True, email=user.email)
            if sent:
                messages.success(request, "Almost there. Check your email and verify your account before logging in.")
            else:
                messages.info(request, "Account created. Please use the verification email to activate login.")
            return redirect("login")
        add_form_error_messages(request, form, "Signup could not be completed.")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


class TennisPrataLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = ContactLoginForm

    def get_success_url(self):
        next_invite = self.request.session.pop("next_invite", None)
        next_pair_invite = self.request.session.pop("next_pair_invite", None)
        return next_invite or next_pair_invite or super().get_success_url()


class TennisPrataLogoutView(LogoutView):
    pass


@staff_member_required(login_url="login")
def moderation_dashboard(request):
    if request.method == "POST":
        form = BlockedIdentityForm(request.POST)
        if form.is_valid():
            blocked = form.save(commit=False)
            blocked.created_by = request.user
            blocked.save()
            messages.success(request, f"Blocked {blocked.value}.")
            return redirect("moderation_dashboard")
    else:
        form = BlockedIdentityForm()

    sessions = PrataSession.objects.select_related("host", "host_pair", "challenger_pair").order_by("-created_at")[:80]
    users = User.objects.select_related("profile").order_by("-date_joined")[:80]
    blocked_identities = BlockedIdentity.objects.select_related("created_by")[:120]
    return render(
        request,
        "play/moderation/dashboard.html",
        {
            "sessions": sessions,
            "users": users,
            "blocked_identities": blocked_identities,
            "block_form": form,
        },
    )


@staff_member_required(login_url="login")
def moderation_cancel_session(request, pk):
    session = get_object_or_404(PrataSession, pk=pk)
    if request.method == "POST":
        form = CancelSessionForm(request.POST)
        if form.is_valid():
            session.status = PrataSession.Status.CANCELLED
            session.cancelled_by = request.user
            session.cancelled_at = timezone.now()
            session.cancel_reason = form.cleaned_data["reason"]
            session.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])
            ChatMessage.objects.create(
                session=session,
                author=request.user,
                is_system=True,
                body=f"Session cancelled by moderation. {session.cancel_reason}".strip(),
            )
            messages.success(request, "Session cancelled.")
            return redirect("moderation_dashboard")
    else:
        form = CancelSessionForm()
    return render(request, "play/moderation/cancel_session.html", {"session": session, "form": form})


@staff_member_required(login_url="login")
def moderation_disable_user(request, user_id):
    target = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    if target == request.user:
        messages.error(request, "You cannot disable your own account from here.")
        return redirect("moderation_dashboard")

    if request.method == "POST":
        form = DisableUserForm(request.POST)
        if form.is_valid():
            target.is_active = False
            target.save(update_fields=["is_active"])
            reason = form.cleaned_data["reason"]
            if form.cleaned_data["block_email"] and target.email:
                BlockedIdentity.objects.update_or_create(
                    identity_type=BlockedIdentity.IdentityType.EMAIL,
                    value=normalize_identity(BlockedIdentity.IdentityType.EMAIL, target.email),
                    defaults={"reason": reason, "created_by": request.user},
                )
            messages.success(request, f"Disabled {target.get_full_name() or target.username}.")
            return redirect("moderation_dashboard")
    else:
        form = DisableUserForm()
    return render(request, "play/moderation/disable_user.html", {"target": target, "form": form})


@staff_member_required(login_url="login")
def moderation_unblock_identity(request, pk):
    blocked = get_object_or_404(BlockedIdentity, pk=pk)
    if request.method == "POST":
        value = blocked.value
        blocked.delete()
        messages.success(request, f"Unblocked {value}.")
    return redirect("moderation_dashboard")


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            previous_email = request.user.email
            form.save()
            if previous_email.lower() != request.user.email.lower():
                create_unverified_primary_email(request.user)
                send_email_confirmation(request, request.user, email=request.user.email)
                messages.success(request, "Profile updated. Please verify your new email before your next login.")
            else:
                messages.success(request, "Profile updated.")
            return redirect("profile")
        add_form_error_messages(request, form, "Profile could not be updated.")
    else:
        form = ProfileForm(instance=profile_obj)

    pairs = Pair.objects.filter(players=request.user).order_by("status", "name")
    notifications = Notification.objects.filter(user=request.user)[:6]
    stats = player_match_stats(request.user)
    reputation = testimonial_summary(request.user)
    pair_invites = pending_pair_invites_for(request.user)
    return render(
        request,
        "play/profile.html",
        {
            "form": form,
            "profile_obj": profile_obj,
            "pairs": pairs,
            "notifications": notifications,
            "stats": stats,
            "reputation": reputation,
            "pair_invites": pair_invites,
        },
    )


@login_required
def notification_preferences(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = NotificationPreferencesForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Notification preferences updated.")
            return redirect("notification_preferences")
        add_form_error_messages(request, form, "Notification preferences could not be updated.")
    else:
        form = NotificationPreferencesForm(instance=profile_obj)
    deliveries = ReminderLog.objects.filter(user=request.user).select_related("session")[:12]
    notifications = Notification.objects.filter(user=request.user)[:12]
    return render(
        request,
        "play/notification_preferences.html",
        {
            "form": form,
            "profile_obj": profile_obj,
            "deliveries": deliveries,
            "notifications": notifications,
        },
    )


@login_required
def create_pair(request):
    group = ensure_demo_group(request.user)
    if request.method == "POST":
        form = PairForm(request.POST)
        if form.is_valid():
            pair = form.save(commit=False)
            pair.group = group
            apply_partner_invite(pair, form.cleaned_data.get("partner_name", ""), form.cleaned_data.get("partner_contact", ""))
            pair.save()
            pair.players.add(request.user)
            if pair.status == Pair.Status.PENDING:
                messages.success(request, f"Pair saved. Share this invite with your partner: {request.build_absolute_uri(pair.accept_url)}")
            else:
                messages.success(request, "Pair saved.")
            return redirect("dashboard")
        add_form_error_messages(request, form, "Pair could not be saved.")
    else:
        form = PairForm()
    return render(request, "play/pair_form.html", {"form": form, "group": group})


def apply_partner_invite(pair, partner_name="", partner_contact=""):
    partner_contact = (partner_contact or "").strip()
    pair.invited_name = (partner_name or "").strip()
    pair.invited_email = partner_contact.lower()
    pair.invited_phone = ""
    pair.status = Pair.Status.PENDING if partner_contact else Pair.Status.CONFIRMED


def rotate_pair_invite(pair):
    pair.invite_code = secrets.token_urlsafe(8)
    while Pair.objects.filter(invite_code=pair.invite_code).exclude(pk=pair.pk).exists():
        pair.invite_code = secrets.token_urlsafe(8)


def add_invited_existing_user(pair):
    invited_user = None
    if pair.invited_email:
        invited_user = User.objects.filter(email__iexact=pair.invited_email).first()
    if invited_user:
        pair.players.add(invited_user)


def accept_pair_invite(request, invite_code):
    pair = get_object_or_404(Pair.objects.select_related("group").prefetch_related("players__profile"), invite_code=invite_code)
    if not request.user.is_authenticated:
        request.session["next_pair_invite"] = request.path
        return render(request, "play/pair_invite_gate.html", {"pair": pair})

    ensure_demo_group(request.user)
    if pair.players.filter(pk=request.user.pk).exists():
        if request.method == "POST":
            messages.info(request, f"You are already listed on {pair.name}.")
            return redirect("pair_detail", pk=pair.pk)
        return render(request, "play/pair_invite.html", {"pair": pair, "already_joined": True, "can_view_pair": True})
    if pair.players.count() >= 2:
        if request.method == "POST":
            messages.info(request, f"{pair.name} is already confirmed.")
            return redirect("dashboard")
        return render(
            request,
            "play/pair_invite.html",
            {"pair": pair, "invite_full": True, "can_view_pair": request.user.is_staff},
        )
    if request.method != "POST":
        return render(request, "play/pair_invite.html", {"pair": pair, "can_view_pair": False})

    existing_players = list(pair.players.all())
    pair.players.add(request.user)
    pair.status = Pair.Status.CONFIRMED
    pair.is_regular = True
    pair.save(update_fields=["status", "is_regular"])
    joiner_name = request.user.get_full_name() or request.user.username
    for player in existing_players:
        create_notification(
            player,
            "Pair invite accepted",
            f"{joiner_name} joined {pair.name}. Your pair is now confirmed.",
            pair.get_absolute_url() if hasattr(pair, "get_absolute_url") else f"/pairs/{pair.pk}/",
        )
    return redirect("pair_invite_accepted", pk=pair.pk)


@login_required
def pair_invite_accepted(request, pk):
    pair = get_object_or_404(Pair.objects.select_related("group").prefetch_related("players__profile"), pk=pk)
    if not pair.players.filter(pk=request.user.pk).exists() and not request.user.is_staff:
        raise PermissionDenied("Only pair members or moderators can view this pair.")
    return render(request, "play/pair_invite_accepted.html", {"pair": pair})


@login_required
def pair_detail(request, pk):
    pair = get_object_or_404(Pair.objects.select_related("group").prefetch_related("players__profile"), pk=pk)
    if not pair.players.filter(pk=request.user.pk).exists() and not request.user.is_staff:
        raise PermissionDenied("Only pair members or moderators can view this pair.")
    matches = PrataSession.objects.filter(host_pair=pair) | PrataSession.objects.filter(challenger_pair=pair)
    matches = matches.distinct().order_by("-starts_at")[:10]
    can_manage_invite = pair.players.filter(pk=request.user.pk).exists() and pair.needs_partner
    return render(
        request,
        "play/pair_detail.html",
        {
            "pair": pair,
            "matches": matches,
            "can_leave_pair": pair.players.filter(pk=request.user.pk).exists(),
            "can_manage_invite": can_manage_invite,
            "invite_form": PairInviteForm(
                initial={"partner_name": pair.invited_name, "partner_contact": pair.invited_email}
            ),
        },
    )


@login_required
def update_pair_invite(request, pk):
    pair = get_object_or_404(Pair.objects.select_related("group"), pk=pk)
    if not pair.players.filter(pk=request.user.pk).exists():
        raise PermissionDenied("Only pair members can invite a new partner.")
    if not pair.needs_partner:
        messages.info(request, f"{pair.name} already has two players.")
        return redirect("pair_detail", pk=pair.pk)
    if request.method != "POST":
        return redirect("pair_detail", pk=pair.pk)

    form = PairInviteForm(request.POST)
    if form.is_valid():
        rotate_pair_invite(pair)
        pair.invited_name = form.cleaned_data.get("partner_name", "").strip()
        partner_contact = form.cleaned_data.get("partner_contact", "").strip()
        pair.invited_email = partner_contact.lower()
        pair.invited_phone = ""
        pair.status = Pair.Status.PENDING
        pair.save(update_fields=["invite_code", "invited_name", "invited_email", "invited_phone", "status"])
        messages.success(request, "Invite link refreshed. Share it with your new partner.")
    else:
        add_form_error_messages(request, form, "Invite could not be updated.")
    return redirect("pair_detail", pk=pair.pk)


@login_required
def leave_pair(request, pk):
    pair = get_object_or_404(Pair.objects.select_related("group").prefetch_related("players__profile"), pk=pk)
    if not pair.players.filter(pk=request.user.pk).exists():
        raise PermissionDenied("Only pair members can leave this pair.")
    if request.method != "POST":
        return render(request, "play/leave_pair.html", {"pair": pair})

    leaving_name = request.user.get_full_name() or request.user.username
    pair.players.remove(request.user)
    remaining_members = list(pair.players.all())
    remaining_players = pair.players.count()
    update_fields = ["invite_code", "invited_name", "invited_email", "invited_phone"]
    rotate_pair_invite(pair)
    pair.invited_name = ""
    pair.invited_email = ""
    pair.invited_phone = ""
    if remaining_players < 2 and pair.status == Pair.Status.CONFIRMED:
        pair.status = Pair.Status.PENDING
        update_fields.append("status")
    if remaining_players == 0 and pair.is_regular:
        pair.is_regular = False
        update_fields.append("is_regular")
    if update_fields:
        pair.save(update_fields=update_fields)
    for player in remaining_members:
        create_notification(
            player,
            "Partner left pair",
            f"{leaving_name} left {pair.name}. Your pair needs a new partner before it can join confirmed challenges.",
            f"/pairs/{pair.pk}/",
        )

    messages.success(request, f"You left {pair.name}.")
    return redirect("profile")


@login_required
def create_session(request):
    group = ensure_demo_group(request.user)

    if request.method == "POST":
        form = PrataSessionForm(request.POST, group=group, user=request.user)
        if form.is_valid():
            session = form.save(commit=False)
            session.group = group
            session.host = request.user
            if session.is_singles:
                session.host_pair = None
            summary, risk = weather_risk_for(session.locality)
            session.weather_summary = summary
            session.weather_risk = risk
            session.save()
            SessionParticipant.objects.get_or_create(
                session=session,
                user=request.user,
                defaults={
                    "pair": session.host_pair if session.is_doubles else None,
                    "side": SessionParticipant.Side.HOST,
                },
            )
            opened_by = session.host_side_name
            ChatMessage.objects.create(
                session=session,
                is_system=True,
                body=f"{opened_by} opened the prata challenge.",
            )
            messages.success(request, "Challenge created. Share the invite link with a challenger.")
            return redirect(session)
        add_form_error_messages(request, form, "Challenge could not be created.")
    else:
        form = PrataSessionForm(group=group, user=request.user)
    return render(request, "play/session_form.html", {"form": form, "group": group})


@login_required
def edit_session(request, pk):
    session = get_object_or_404(PrataSession.objects.select_related("group", "host"), pk=pk)
    if session.host != request.user and not request.user.is_staff:
        raise PermissionDenied("Only the host or a moderator can edit this session.")

    if request.method == "POST":
        form = PrataSessionForm(request.POST, group=session.group, user=request.user, instance=session)
        if form.is_valid():
            session = form.save(commit=False)
            if session.is_singles:
                session.host_pair = None
                session.challenger_pair = None
            else:
                session.challenger_player = None
            summary, risk = weather_risk_for(session.locality or session.court_name)
            session.weather_summary = summary
            session.weather_risk = risk
            session.save()
            messages.success(request, "Session updated.")
            return redirect(session)
        add_form_error_messages(request, form, "Session could not be saved.")
    else:
        form = PrataSessionForm(group=session.group, user=request.user, instance=session)
    return render(request, "play/session_form.html", {"form": form, "group": session.group, "session": session, "is_edit": True})


def join_invite(request, invite_code):
    session = get_object_or_404(
        PrataSession.objects.select_related("group", "host", "host_pair", "challenger_player"),
        invite_code=invite_code,
    )
    if not request.user.is_authenticated:
        request.session["next_invite"] = request.path
        return render(request, "play/session_invite_gate.html", {"session": session})

    ensure_demo_group(request.user)
    user_pairs = session.group.pairs.filter(players=request.user, status=Pair.Status.CONFIRMED).exclude(
        name__icontains="/ TBD"
    )
    is_host = session.host_id == request.user.id or (
        session.host_pair and session.host_pair.players.filter(pk=request.user.pk).exists()
    )
    if request.method == "POST":
        if is_host:
            messages.info(request, "You are hosting this challenge. Share the invite link with another pair.")
            return redirect(session)
        if session.is_singles:
            if session.challenger_player:
                messages.info(request, "This singles challenge already has a challenger.")
                return redirect(session)
            participant, _ = SessionParticipant.objects.update_or_create(
                session=session,
                user=request.user,
                defaults={
                    "pair": None,
                    "side": SessionParticipant.Side.CHALLENGER,
                    "status": SessionParticipant.Status.CONFIRMED,
                },
            )
            session.challenger_player = request.user
            session.status = PrataSession.Status.CONFIRMED
            session.save(update_fields=["challenger_player", "status"])
            ChatMessage.objects.create(
                session=session,
                is_system=True,
                body=f"{request.user.get_full_name() or request.user.username} joined as the challenger.",
            )
            notify_host_side_session_joined(
                session,
                request.user.get_full_name() or request.user.username,
                actor=request.user,
            )
            return redirect("session_invite_accepted", pk=session.pk)
        form = JoinSessionForm(request.POST, group=session.group, user=request.user)
        if session.challenger_pair:
            messages.info(request, "This challenge already has a challenger pair.")
            return redirect(session)
        if form.is_valid():
            pair = form.cleaned_data["saved_pair"]
            SessionParticipant.objects.update_or_create(
                session=session,
                user=request.user,
                defaults={
                    "pair": pair,
                    "side": SessionParticipant.Side.CHALLENGER,
                    "status": SessionParticipant.Status.CONFIRMED,
                },
            )
            session.challenger_pair = pair
            session.status = PrataSession.Status.CONFIRMED
            session.save(update_fields=["challenger_pair", "status"])
            ChatMessage.objects.create(session=session, is_system=True, body=f"{pair} joined as the challenger pair.")
            notify_host_side_session_joined(session, str(pair), actor=request.user)
            return redirect("session_invite_accepted", pk=session.pk)
        add_form_error_messages(request, form, "Could not join the challenge.")
    else:
        form = JoinSessionForm(group=session.group, user=request.user)
    return render(
        request,
        "play/join_invite.html",
        {"session": session, "form": form, "user_pairs": user_pairs, "is_host": is_host},
    )


@login_required
def session_invite_accepted(request, pk):
    session = get_object_or_404(
        PrataSession.objects.select_related("group", "host", "host_pair", "challenger_pair", "challenger_player"),
        pk=pk,
    )
    if not session.participants.filter(user=request.user).exists() and not request.user.is_staff:
        raise PermissionDenied("Only session participants or moderators can view this confirmation.")
    return render(request, "play/session_invite_accepted.html", {"session": session})


def session_detail(request, pk):
    session = get_object_or_404(
        PrataSession.objects.select_related("group", "host", "host_pair", "challenger_pair", "challenger_player", "result"),
        pk=pk,
    )
    if not request.user.is_authenticated:
        request.session["next_invite"] = request.path
        return render(request, "play/session_invite_gate.html", {"session": session, "hide_details": True})
    if not user_can_view_session_detail(request.user, session):
        raise PermissionDenied("Use the private invite link to join this challenge.")
    result = getattr(session, "result", None)
    chat_form = ChatMessageForm()
    score_form = MatchScoreForm(session=session)
    has_started = session_has_started(session)
    players = session_player_users(session)
    match_sides = session_match_sides(session)
    if request.method == "POST" and request.user.is_authenticated:
        action = request.POST.get("action")
        if action == "chat":
            if not user_can_access_session_chat(request.user, session):
                raise PermissionDenied("Only session players can use this chat.")
            chat_form = ChatMessageForm(request.POST)
            if chat_form.is_valid():
                message = chat_form.save(commit=False)
                message.session = session
                message.author = request.user
                message.save()
                return redirect(session)
        elif action == "score":
            if not has_started:
                messages.info(request, "Scores can be added after the scheduled start time.")
                return redirect(session)
            if not session_has_challenger(session):
                messages.info(request, "Add a challenger before recording a score.")
                return redirect(session)
            if not user_can_submit_post_match(request.user, session):
                raise PermissionDenied("Only session players or moderators can record scores.")
            score_form = MatchScoreForm(request.POST, session=session)
            if score_form.is_valid():
                apply_score_result(session, request.user, score_form)
                messages.success(request, "Score saved. Add shoutouts while the match is fresh.")
                return redirect(f"{session.get_absolute_url()}#shoutouts")
            add_form_error_messages(request, score_form, "Score could not be saved.")
        elif action == "testimonial":
            if not result:
                messages.info(request, "Testimonials open after a result is recorded.")
                return redirect(session)
            if request.user not in players and not request.user.is_staff:
                raise PermissionDenied("Only session players can leave testimonials.")
            reviewed_user = get_object_or_404(User, pk=request.POST.get("reviewed_user_id"))
            if reviewed_user == request.user:
                messages.error(request, "You cannot review yourself.")
                return redirect(session)
            if reviewed_user not in players:
                raise PermissionDenied("Testimonials are only for players in this match.")
            testimonial_form = TestimonialForm(request.POST, prefix=f"testimonial_{reviewed_user.pk}")
            if testimonial_form.is_valid():
                testimonial, _ = Testimonial.objects.update_or_create(
                    session=session,
                    reviewer=request.user,
                    reviewed_user=reviewed_user,
                    defaults={
                        "rating": testimonial_form.cleaned_data["rating"],
                        "badges": testimonial_form.cleaned_data["badges"],
                        "text": testimonial_form.cleaned_data["text"],
                    },
                )
                messages.success(request, f"Shoutout saved for {testimonial.reviewed_user.get_full_name() or testimonial.reviewed_user.username}.")
                return redirect(f"{session.get_absolute_url()}#shoutouts")
            add_form_error_messages(request, testimonial_form, "Shoutout could not be saved.")

    participants = session.participants.select_related("user", "pair", "user__profile")
    can_edit_session = request.user.is_authenticated and (session.host == request.user or request.user.is_staff)
    can_record_score = (
        request.user.is_authenticated
        and has_started
        and not result
        and session_has_challenger(session)
        and user_can_submit_post_match(request.user, session)
    )
    can_cancel_session = (
        user_can_cancel_session(request.user, session)
        and session.status not in (PrataSession.Status.CANCELLED, PrataSession.Status.COMPLETED)
        and not result
    )
    can_join_session = user_can_join_session(request.user, session, result)
    can_access_chat = user_can_access_session_chat(request.user, session)
    can_withdraw_session = (
        request.user.is_authenticated
        and (session.challenger_pair or session.challenger_player)
        and not result
        and session.status != PrataSession.Status.COMPLETED
        and (
            (session.is_doubles and session.challenger_pair and session.challenger_pair.players.filter(pk=request.user.pk).exists())
            or (session.is_singles and session.challenger_player_id == request.user.id)
        )
    )
    testimonial_items = []
    can_leave_testimonials = bool(result and request.user.is_authenticated and request.user in players)
    if can_leave_testimonials:
        existing_testimonials = {
            testimonial.reviewed_user_id: testimonial
            for testimonial in Testimonial.objects.filter(session=session, reviewer=request.user)
        }
        for player in players:
            if player == request.user:
                continue
            existing = existing_testimonials.get(player.pk)
            testimonial_items.append(
                {
                    "player": player,
                    "existing": existing,
                    "form": TestimonialForm(
                        instance=existing,
                        initial={"badges": existing.badges if existing else []},
                        prefix=f"testimonial_{player.pk}",
                    ),
                }
            )
    received_testimonials = session.testimonials.select_related("reviewer", "reviewed_user")
    return render(
        request,
        "play/session_detail.html",
        {
            "session": session,
            "participants": participants,
            "session_players": players,
            "match_sides": match_sides,
            "chat_form": chat_form,
            "score_form": score_form,
            "result": result,
            "has_started": has_started,
            "can_record_score": can_record_score,
            "can_edit_session": can_edit_session,
            "can_cancel_session": can_cancel_session,
            "can_join_session": can_join_session,
            "can_access_chat": can_access_chat,
            "can_withdraw_session": can_withdraw_session,
            "testimonial_items": testimonial_items,
            "received_testimonials": received_testimonials,
        },
    )


@login_required
def cancel_session(request, pk):
    session = get_object_or_404(
        PrataSession.objects.select_related(
            "group", "host", "host_pair", "challenger_pair", "challenger_player", "result"
        ).prefetch_related(
            "participants__user"
        ),
        pk=pk,
    )
    result = getattr(session, "result", None)
    if not user_can_cancel_session(request.user, session):
        raise PermissionDenied("Only the creator pair can cancel this challenge.")
    if result or session.status == PrataSession.Status.COMPLETED:
        messages.info(request, "Completed challenges cannot be cancelled or deleted.")
        return redirect(session)
    if session.status == PrataSession.Status.CANCELLED:
        messages.info(request, "This challenge is already cancelled.")
        return redirect(session)

    can_delete_session = session.challenger_pair_id is None and session.challenger_player_id is None
    if request.method != "POST":
        form = CancelSessionForm()
        return render(
            request,
            "play/cancel_session.html",
            {"session": session, "form": form, "can_delete_session": can_delete_session},
        )

    action = request.POST.get("action", "cancel")
    if action == "delete":
        if not can_delete_session:
            messages.error(request, "Only open challenges without a challenger pair can be deleted.")
            return redirect(session)
        title = session.title
        session.delete()
        messages.success(request, f"Deleted {title}.")
        return redirect("dashboard")

    form = CancelSessionForm(request.POST)
    if form.is_valid():
        session.status = PrataSession.Status.CANCELLED
        session.cancelled_by = request.user
        session.cancelled_at = timezone.now()
        session.cancel_reason = form.cleaned_data["reason"]
        session.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])
        ChatMessage.objects.create(
            session=session,
            author=request.user,
            is_system=True,
            body=f"Challenge cancelled by creator pair. {session.cancel_reason}".strip(),
        )
        notified_users = {
            participant.user
            for participant in session.participants.select_related("user")
            if participant.user_id != request.user.id
        }
        for user in notified_users:
            create_notification(
                user,
                "Challenge cancelled",
                f"{session.title} was cancelled by the creator pair.",
                session.get_absolute_url(),
            )
        messages.success(request, "Challenge cancelled.")
        return redirect(session)
    add_form_error_messages(request, form, "Challenge could not be cancelled.")
    return render(
        request,
        "play/cancel_session.html",
        {"session": session, "form": form, "can_delete_session": can_delete_session},
    )


@login_required
def withdraw_session(request, pk):
    session = get_object_or_404(
        PrataSession.objects.select_related("group", "host", "host_pair", "challenger_pair", "challenger_player", "result"),
        pk=pk,
    )
    result = getattr(session, "result", None)
    if not session.challenger_pair and not session.challenger_player:
        messages.info(request, "This challenge does not have a challenger yet.")
        return redirect(session)
    if result or session.status == PrataSession.Status.COMPLETED:
        messages.info(request, "Completed challenges cannot be withdrawn.")
        return redirect(session)
    can_withdraw = (
        (session.is_doubles and session.challenger_pair and session.challenger_pair.players.filter(pk=request.user.pk).exists())
        or (session.is_singles and session.challenger_player_id == request.user.id)
        or request.user.is_staff
    )
    if not can_withdraw:
        raise PermissionDenied("Only the challenger pair or a moderator can withdraw from this challenge.")
    if request.method != "POST":
        return render(request, "play/withdraw_session.html", {"session": session})

    withdrawn_side = session.challenger_side_name
    if session.is_doubles:
        SessionParticipant.objects.filter(
            session=session,
            pair=session.challenger_pair,
            side=SessionParticipant.Side.CHALLENGER,
        ).delete()
        session.challenger_pair = None
        update_fields = ["challenger_pair", "status"]
    else:
        SessionParticipant.objects.filter(
            session=session,
            user=session.challenger_player,
            side=SessionParticipant.Side.CHALLENGER,
        ).delete()
        session.challenger_player = None
        update_fields = ["challenger_player", "status"]
    session.status = PrataSession.Status.OPEN
    session.save(update_fields=update_fields)
    ChatMessage.objects.create(
        session=session,
        is_system=True,
        body=f"{withdrawn_side} withdrew from the challenge. Challenger side is open again.",
    )
    create_notification(
        session.host,
        "Challenger withdrew",
        f"{withdrawn_side} withdrew from {session.title}. The challenger side is open again.",
        session.get_absolute_url(),
    )
    messages.success(request, f"{withdrawn_side} withdrew from the challenge.")
    return redirect(session)

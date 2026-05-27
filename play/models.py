import secrets

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

NTRP_LEVEL_CHOICES = [("beginner", "Beginner")] + [(f"{level / 10:.1f}", f"{level / 10:.1f}") for level in range(25, 46)]

TESTIMONIAL_BADGE_CHOICES = (
    ("team_player", "Team player"),
    ("super_forehand", "Super forehand"),
    ("super_backhand", "Super backhand"),
    ("big_serve", "Big serve"),
    ("net_ninja", "Net ninja"),
    ("court_coverage", "Great court coverage"),
    ("positive_energy", "Positive energy"),
    ("fair_play", "Fair play"),
    ("clutch", "Clutch under pressure"),
    ("prata_spirit", "Prata spirit"),
)


class Profile(models.Model):
    class NtrpLevel(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        TWO_FIVE = "2.5", "2.5"
        THREE_ZERO = "3.0", "3.0"
        THREE_FIVE = "3.5", "3.5"
        FOUR_ZERO = "4.0", "4.0"
        FOUR_FIVE = "4.5", "4.5+"

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    ntrp_level = models.CharField(max_length=16, choices=NTRP_LEVEL_CHOICES, default=NtrpLevel.THREE_ZERO)
    home_courts = models.CharField(max_length=160, blank=True)
    bio = models.TextField(blank=True)
    reminders_by_email = models.BooleanField(default=True)
    reminders_by_sms = models.BooleanField(default=False)
    reminders_by_whatsapp = models.BooleanField(default=False)
    reminders_by_calendar = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class PlayGroup(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, through="GroupMembership", related_name="play_groups")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    class Role(models.TextChoices):
        MEMBER = "member", "Member"
        ORGANIZER = "organizer", "Organizer"

    group = models.ForeignKey(PlayGroup, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "user")


class Pair(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending partner"
        CONFIRMED = "confirmed", "Confirmed"
        AD_HOC = "ad_hoc", "Ad hoc"

    group = models.ForeignKey(PlayGroup, on_delete=models.CASCADE, related_name="pairs")
    name = models.CharField(max_length=140)
    players = models.ManyToManyField(User, related_name="pairs", blank=True)
    is_regular = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
    invited_name = models.CharField(max_length=120, blank=True)
    invited_email = models.EmailField(blank=True)
    invited_phone = models.CharField(max_length=32, blank=True)
    invite_code = models.CharField(max_length=16, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(8)
        super().save(*args, **kwargs)

    @property
    def accept_url(self):
        return reverse("accept_pair_invite", args=[self.invite_code])

    def get_absolute_url(self):
        return reverse("pair_detail", args=[self.pk])

    @property
    def wins(self):
        return self.won_results.count()

    @property
    def losses(self):
        return self.lost_results.count()

    @property
    def points(self):
        return self.wins * 3 + self.losses

    @property
    def needs_partner(self):
        return self.status == self.Status.PENDING and self.players.count() < 2

    @property
    def display_name(self):
        if self.needs_partner:
            players = list(self.players.all())
            if players:
                remaining_player = players[0].get_full_name() or players[0].username
                return f"{remaining_player} / Partner needed"
        return self.name


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=260)
    url = models.CharField(max_length=220, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class PrataSession(models.Model):
    class MatchType(models.TextChoices):
        SINGLES = "singles", "Singles"
        DOUBLES = "doubles", "Doubles"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    group = models.ForeignKey(PlayGroup, on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(max_length=140)
    match_type = models.CharField(max_length=16, choices=MatchType.choices, default=MatchType.DOUBLES)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name="hosted_sessions")
    host_pair = models.ForeignKey(Pair, on_delete=models.PROTECT, related_name="hosted_sessions", null=True, blank=True)
    challenger_pair = models.ForeignKey(
        Pair,
        on_delete=models.PROTECT,
        related_name="challenged_sessions",
        null=True,
        blank=True,
    )
    challenger_player = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="challenged_singles_sessions",
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField()
    locality = models.CharField(max_length=80)
    court_name = models.CharField(max_length=160)
    court_details = models.CharField(max_length=220, blank=True)
    court_address = models.CharField(max_length=260, blank=True)
    postal_code = models.CharField(max_length=12, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    google_place_id = models.CharField(max_length=160, blank=True)
    cost_notes = models.CharField(max_length=160, blank=True)
    level_min = models.CharField(max_length=16, choices=NTRP_LEVEL_CHOICES, default=Profile.NtrpLevel.TWO_FIVE)
    level_max = models.CharField(max_length=16, choices=NTRP_LEVEL_CHOICES, default=Profile.NtrpLevel.FOUR_FIVE)
    prata_terms = models.CharField(
        max_length=180,
        blank=True,
        default="Optional: losing pair treats prata, teh, or just accepts light-hearted banter.",
    )
    notes = models.TextField(blank=True)
    invite_code = models.CharField(max_length=16, unique=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    weather_summary = models.CharField(max_length=120, blank=True)
    weather_risk = models.CharField(max_length=32, default="Pending")
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_sessions",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=220, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at",)

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(8)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("session_detail", args=[self.pk])

    @property
    def invite_url(self):
        return reverse("join_invite", args=[self.invite_code])

    @property
    def is_singles(self):
        return self.match_type == self.MatchType.SINGLES

    @property
    def is_doubles(self):
        return self.match_type == self.MatchType.DOUBLES

    @property
    def host_side_name(self):
        if self.is_singles:
            return self.host.get_full_name() or self.host.username
        return str(self.host_pair) if self.host_pair else "Host pair"

    @property
    def challenger_side_name(self):
        if self.is_singles:
            return (
                self.challenger_player.get_full_name() or self.challenger_player.username
                if self.challenger_player
                else "Open challenger"
            )
        return str(self.challenger_pair) if self.challenger_pair else "Open challenger side"

    @property
    def needs_reminder(self):
        window_start = timezone.now()
        window_end = window_start + timezone.timedelta(hours=24, minutes=15)
        return self.reminder_sent_at is None and window_start < self.starts_at <= window_end


class SessionParticipant(models.Model):
    class Side(models.TextChoices):
        HOST = "host", "Host"
        CHALLENGER = "challenger", "Challenger"
        SOLO_POOL = "solo_pool", "Looking for partner"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"

    session = models.ForeignKey(PrataSession, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    pair = models.ForeignKey(Pair, on_delete=models.SET_NULL, null=True, blank=True)
    side = models.CharField(max_length=24, choices=Side.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "user")


class ChatMessage(models.Model):
    session = models.ForeignKey(PrataSession, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    body = models.TextField()
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class SessionPhoto(models.Model):
    session = models.ForeignKey(PrataSession, on_delete=models.CASCADE, related_name="photos")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="session_photos")
    image = models.ImageField(upload_to="session_photos/")
    caption = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Photo for {self.session}"


class MatchResult(models.Model):
    class WinnerSide(models.TextChoices):
        HOST = "host", "Host side"
        CHALLENGER = "challenger", "Challenger side"

    session = models.OneToOneField(PrataSession, on_delete=models.CASCADE, related_name="result")
    winner_side = models.CharField(max_length=16, choices=WinnerSide.choices, default=WinnerSide.HOST)
    winning_pair = models.ForeignKey(
        Pair,
        on_delete=models.PROTECT,
        related_name="won_results",
        null=True,
        blank=True,
    )
    losing_pair = models.ForeignKey(
        Pair,
        on_delete=models.PROTECT,
        related_name="lost_results",
        null=True,
        blank=True,
    )
    winning_player = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="won_singles_results",
        null=True,
        blank=True,
    )
    losing_player = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lost_singles_results",
        null=True,
        blank=True,
    )
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    confirmed_at = models.DateTimeField(auto_now_add=True)

    @property
    def winner_name(self):
        if self.session.is_singles:
            return self.winning_player.get_full_name() or self.winning_player.username if self.winning_player else "Winner"
        return str(self.winning_pair) if self.winning_pair else "Winner"

    @property
    def loser_name(self):
        if self.session.is_singles:
            return self.losing_player.get_full_name() or self.losing_player.username if self.losing_player else "Opponent"
        return str(self.losing_pair) if self.losing_pair else "Opponent"

    @property
    def score_summary(self):
        scores = [f"{score.host_score}-{score.challenger_score}" for score in self.set_scores.all()]
        return ", ".join(scores)


class MatchSetScore(models.Model):
    result = models.ForeignKey(MatchResult, on_delete=models.CASCADE, related_name="set_scores")
    set_number = models.PositiveSmallIntegerField()
    host_score = models.PositiveSmallIntegerField()
    challenger_score = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("set_number",)
        unique_together = ("result", "set_number")

    def __str__(self):
        return f"Set {self.set_number}: {self.host_score}-{self.challenger_score}"


class Testimonial(models.Model):
    session = models.ForeignKey(PrataSession, on_delete=models.CASCADE, related_name="testimonials")
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="given_testimonials")
    reviewed_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_testimonials")
    rating = models.PositiveSmallIntegerField()
    badges = models.JSONField(default=list)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("session", "reviewer", "reviewed_user")

    @property
    def badge_labels(self):
        labels = dict(TESTIMONIAL_BADGE_CHOICES)
        return [labels.get(badge, badge) for badge in self.badges]


class ReminderLog(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"
        CALENDAR = "calendar", "Calendar invite"

    session = models.ForeignKey(PrataSession, on_delete=models.CASCADE, related_name="reminder_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    destination = models.CharField(max_length=180)
    sent_at = models.DateTimeField(auto_now_add=True)
    provider_message_id = models.CharField(max_length=120, blank=True)


class BlockedIdentity(models.Model):
    class IdentityType(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    identity_type = models.CharField(max_length=16, choices=IdentityType.choices)
    value = models.CharField(max_length=254)
    reason = models.CharField(max_length=220, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("identity_type", "value")
        ordering = ("identity_type", "value")

    def save(self, *args, **kwargs):
        self.value = normalize_identity(self.identity_type, self.value)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_identity_type_display()}: {self.value}"


def normalize_identity(identity_type, value):
    value = (value or "").strip()
    if identity_type == BlockedIdentity.IdentityType.EMAIL:
        return value.lower()
    return value

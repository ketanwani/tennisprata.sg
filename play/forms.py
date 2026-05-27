from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from PIL import Image, UnidentifiedImageError

from .identity import email_address_is_verified
from .models import (
    BlockedIdentity,
    ChatMessage,
    MatchResult,
    NTRP_LEVEL_CHOICES,
    Pair,
    PrataSession,
    Profile,
    TESTIMONIAL_BADGE_CHOICES,
    Testimonial,
    normalize_identity,
)

MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 2000
ALLOWED_AVATAR_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 8_000_000


class SignupForm(UserCreationForm):
    full_name = forms.CharField(max_length=120, label="Full name")
    email = forms.EmailField(
        required=True,
        label="Email address",
        help_text="We will send a verification link before you can log in.",
    )
    ntrp_level = forms.ChoiceField(
        choices=NTRP_LEVEL_CHOICES,
        label="NTRP level",
        widget=forms.Select(attrs={"data-ntrp-slider": "true"}),
    )

    class Meta:
        model = User
        fields = ("full_name", "email", "ntrp_level", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "full_name": "Full name",
            "email": "Email address",
            "password1": "Create password",
            "password2": "Confirm password",
        }
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs.update({"placeholder": placeholder})

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email", "").strip().lower()
        if not email:
            self.add_error("email", "Email is required to create an account.")
        if email and User.objects.filter(email__iexact=email).exists():
            self.add_error("email", "An account with this email already exists.")
        if email and BlockedIdentity.objects.filter(
            identity_type=BlockedIdentity.IdentityType.EMAIL,
            value=normalize_identity(BlockedIdentity.IdentityType.EMAIL, email),
        ).exists():
            self.add_error("email", "This email cannot register on tennisprata.sg.")
        cleaned["email"] = email
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        names = self.cleaned_data["full_name"].split(" ", 1)
        user.username = self._make_username()
        user.first_name = names[0]
        user.last_name = names[1] if len(names) > 1 else ""
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "phone": "",
                    "ntrp_level": self.cleaned_data["ntrp_level"],
                },
            )
        return user

    def _make_username(self):
        email = self.cleaned_data.get("email")
        seed = email.split("@")[0] if email else "player"
        base = slugify(seed) or "player"
        username = base[:140]
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base[:134]}-{suffix}"
        return username


class ContactLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", max_length=254)

    def clean(self):
        identifier = self.cleaned_data.get("username", "").strip().lower()
        password = self.cleaned_data.get("password")
        username = identifier

        if identifier:
            if BlockedIdentity.objects.filter(
                identity_type=BlockedIdentity.IdentityType.EMAIL,
                value=normalize_identity(BlockedIdentity.IdentityType.EMAIL, identifier),
            ).exists():
                raise ValidationError("This email is not allowed to log in.", code="blocked_login")
            user = User.objects.filter(email__iexact=identifier).first()
            username = user.username if user else identifier

        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise ValidationError(
                    "Please enter a correct email and password.",
                    code="invalid_login",
                )
            self.confirm_login_allowed(self.user_cache)
            if not email_address_is_verified(self.user_cache):
                raise ValidationError(
                    "Please verify your email before logging in.",
                    code="email_not_verified",
                )
        return self.cleaned_data


class BlockedIdentityForm(forms.ModelForm):
    class Meta:
        model = BlockedIdentity
        fields = ("identity_type", "value", "reason")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identity_type"].choices = (
            (BlockedIdentity.IdentityType.EMAIL, "Email"),
        )


class CancelSessionForm(forms.Form):
    reason = forms.CharField(
        max_length=220,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Why is this session being cancelled?"}),
    )


class DisableUserForm(forms.Form):
    reason = forms.CharField(
        max_length=220,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional internal moderation reason"}),
    )
    block_email = forms.BooleanField(required=False, initial=True)


class ProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=120)
    email = forms.EmailField(required=True, help_text="Changing this email requires verification before your next login.")

    class Meta:
        model = Profile
        fields = (
            "full_name",
            "email",
            "phone",
            "avatar",
            "ntrp_level",
            "home_courts",
            "bio",
        )
        labels = {
            "ntrp_level": "NTRP level",
            "home_courts": "Home courts",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields["full_name"].initial = user.get_full_name() or user.username
        self.fields["email"].initial = user.email
        self.fields["ntrp_level"].widget.attrs.update({"data-ntrp-slider": "true"})

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email", "").strip().lower()
        phone = cleaned.get("phone", "").strip()
        if not email:
            self.add_error("email", "Email is required for login and account recovery.")
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.user_id).exists():
            self.add_error("email", "Another account already uses this email.")
        if email and BlockedIdentity.objects.filter(
            identity_type=BlockedIdentity.IdentityType.EMAIL,
            value=normalize_identity(BlockedIdentity.IdentityType.EMAIL, email),
        ).exists():
            self.add_error("email", "This email cannot be used on tennisprata.sg.")
        if phone and Profile.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists():
            self.add_error("phone", "Another account already uses this phone number.")
        if phone and BlockedIdentity.objects.filter(
            identity_type=BlockedIdentity.IdentityType.PHONE,
            value=normalize_identity(BlockedIdentity.IdentityType.PHONE, phone),
        ).exists():
            self.add_error("phone", "This phone number cannot be used on tennisprata.sg.")
        cleaned["email"] = email
        cleaned["phone"] = phone
        return cleaned

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar
        if avatar.size > MAX_AVATAR_BYTES:
            raise forms.ValidationError("Profile photo must be 2 MB or smaller.")
        content_type = getattr(avatar, "content_type", "")
        if content_type and content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
            raise forms.ValidationError("Upload a JPG, PNG, or WebP image.")
        try:
            avatar.seek(0)
            image = Image.open(avatar)
            width, height = image.size
            image_format = image.format
            image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise forms.ValidationError("Upload a valid image file.")
        finally:
            avatar.seek(0)
        if image_format not in ALLOWED_AVATAR_FORMATS:
            raise forms.ValidationError("Upload a JPG, PNG, or WebP image.")
        if width > MAX_AVATAR_DIMENSION or height > MAX_AVATAR_DIMENSION:
            raise forms.ValidationError("Profile photo must be 2000 x 2000 pixels or smaller.")
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=False)
        names = self.cleaned_data["full_name"].split(" ", 1)
        profile.user.first_name = names[0]
        profile.user.last_name = names[1] if len(names) > 1 else ""
        profile.user.email = self.cleaned_data.get("email", "")
        if commit:
            profile.user.save()
            profile.save()
        return profile


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = (
            "reminders_by_email",
            "reminders_by_sms",
            "reminders_by_whatsapp",
            "reminders_by_calendar",
        )
        labels = {
            "reminders_by_email": "Email",
            "reminders_by_sms": "SMS",
            "reminders_by_whatsapp": "WhatsApp",
            "reminders_by_calendar": "Calendar invite",
        }
        help_texts = {
            "reminders_by_email": "Session reminders and important challenge updates.",
            "reminders_by_sms": "Upcoming feature. SMS delivery is not enabled yet.",
            "reminders_by_whatsapp": "Upcoming feature. WhatsApp delivery is not enabled yet.",
            "reminders_by_calendar": "Attach a calendar invite to email reminders.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("reminders_by_sms", "reminders_by_whatsapp"):
            self.fields[field_name].disabled = True
            self.fields[field_name].initial = False
            self.fields[field_name].widget.attrs.update({"disabled": "disabled"})

    def clean(self):
        cleaned = super().clean()
        email = (self.instance.user.email or "").strip()
        cleaned["reminders_by_sms"] = False
        cleaned["reminders_by_whatsapp"] = False
        if cleaned.get("reminders_by_email") and not email:
            self.add_error("reminders_by_email", "Add an email address on your profile to use email reminders.")
        if cleaned.get("reminders_by_calendar") and not email:
            self.add_error("reminders_by_calendar", "Add an email address on your profile to receive calendar invites.")
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.reminders_by_sms = False
        profile.reminders_by_whatsapp = False
        if commit:
            profile.save()
        return profile


class PairForm(forms.ModelForm):
    partner_name = forms.CharField(
        max_length=120,
        required=False,
        label="Partner name",
        help_text="Optional. Use this when your partner has not joined tennisprata.sg yet.",
    )
    partner_contact = forms.CharField(
        max_length=254,
        required=False,
        label="Partner email",
        help_text="If they already have an account, they can accept and join this pair.",
    )

    class Meta:
        model = Pair
        fields = ("name", "is_regular")
        labels = {
            "name": "Pair name",
            "is_regular": "Save this as a regular pair",
        }
        help_texts = {
            "name": "Use both names, like Ketan / Aaron, so it is easy to recognize on challenges.",
        }

    def clean_partner_contact(self):
        partner_contact = self.cleaned_data.get("partner_contact", "").strip().lower()
        if partner_contact:
            validate_email(partner_contact)
        return partner_contact

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_regular"].initial = True


class PairInviteForm(forms.Form):
    partner_name = forms.CharField(
        max_length=120,
        required=False,
        label="Partner name",
        widget=forms.TextInput(attrs={"placeholder": "Partner name"}),
    )
    partner_contact = forms.CharField(
        max_length=254,
        required=False,
        label="Partner email",
        widget=forms.EmailInput(attrs={"placeholder": "Email address"}),
        help_text="Optional for the POC. You can also just copy the invite link.",
    )

    def clean_partner_contact(self):
        partner_contact = self.cleaned_data.get("partner_contact", "").strip().lower()
        if partner_contact:
            validate_email(partner_contact)
        return partner_contact


class PrataSessionForm(forms.ModelForm):
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())
    date = forms.DateField(
        label="Date",
        widget=forms.DateInput(attrs={"type": "date", "class": "date-input"}),
    )
    time = forms.TimeField(
        label="Start time",
        widget=forms.TimeInput(attrs={"type": "time", "class": "time-input"}),
    )

    class Meta:
        model = PrataSession
        fields = (
            "title",
            "match_type",
            "host_pair",
            "date",
            "time",
            "court_name",
            "locality",
            "court_address",
            "postal_code",
            "latitude",
            "longitude",
            "level_min",
            "level_max",
            "prata_terms",
            "notes",
        )

    def __init__(self, *args, group=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.starts_at:
            local_start = timezone.localtime(self.instance.starts_at)
            self.fields["date"].initial = local_start.date()
            self.fields["time"].initial = local_start.time().replace(second=0, microsecond=0)
        if group:
            pairs = group.pairs.filter(status=Pair.Status.CONFIRMED)
            if user and not user.is_staff:
                pairs = pairs.filter(players=user)
            if self.instance and self.instance.pk and self.instance.host_pair_id:
                pairs = pairs | group.pairs.filter(pk=self.instance.host_pair_id)
            pairs = pairs.distinct()
            self.fields["host_pair"].queryset = pairs
            if not pairs.exists():
                self.fields["host_pair"].help_text = "Required for doubles. Create or accept a pair first, then you can host a doubles challenge."
        self.fields["match_type"].label = "Match type"
        self.fields["match_type"].help_text = "Singles is player vs player. Doubles is pair vs pair."
        self.fields["host_pair"].label = "Host pair"
        self.fields["host_pair"].required = False
        self.fields["prata_terms"].label = "Prata vibes"
        self.fields["prata_terms"].help_text = "Fixed for the POC: playful and optional, never compulsory."
        self.fields["prata_terms"].initial = "Optional: losing pair treats prata, teh, or just accepts light-hearted banter."
        self.fields["prata_terms"].required = False
        self.fields["prata_terms"].widget.attrs.update({"readonly": "readonly"})
        self.fields["court_name"].widget.attrs.update(
            {
                "autocomplete": "off",
                "placeholder": "Search court name or Singapore postal code",
                "data-location-search": "true",
            }
        )
        self.fields["court_name"].label = "Play location"
        self.fields["court_name"].help_text = "Search by tennis centre, condo, club, park, or Singapore postal code."
        self.fields["level_min"].label = "Minimum level"
        self.fields["level_max"].label = "Maximum level"
        self.fields["level_min"].widget.attrs.update({"class": "level-select", "data-ntrp-slider": "true"})
        self.fields["level_max"].widget.attrs.update({"class": "level-select", "data-ntrp-slider": "true"})
        for hidden_field in ("locality", "court_address", "postal_code", "latitude", "longitude"):
            self.fields[hidden_field].widget = forms.HiddenInput()
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("match_type") == PrataSession.MatchType.DOUBLES and not cleaned.get("host_pair"):
            self.add_error("host_pair", "Choose a confirmed pair for doubles.")
        return cleaned

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("Pick today or a future date.")
        return date

    def clean_latitude(self):
        return self._clean_coordinate("latitude")

    def clean_longitude(self):
        return self._clean_coordinate("longitude")

    def _clean_coordinate(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Choose a location from the search results.")

    def save(self, commit=True):
        session = super().save(commit=False)
        local_dt = timezone.datetime.combine(self.cleaned_data["date"], self.cleaned_data["time"])
        session.starts_at = timezone.make_aware(local_dt, timezone.get_current_timezone())
        if not session.locality:
            session.locality = session.court_name[:80]
        if commit:
            session.save()
        return session


class JoinSessionForm(forms.Form):
    saved_pair = forms.ModelChoiceField(
        queryset=Pair.objects.none(),
        required=True,
        label="Choose your pair",
        empty_label="Select a confirmed pair",
        help_text="Only confirmed pairs can join prata challenges.",
    )

    def __init__(self, *args, group=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        saved_pairs = Pair.objects.none()
        if group and user:
            saved_pairs = group.pairs.filter(players=user, status=Pair.Status.CONFIRMED).exclude(
                name__icontains="/ TBD"
            )
        self.fields["saved_pair"].queryset = saved_pairs

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("saved_pair"):
            self.add_error("saved_pair", "Choose one of your saved pairs.")
        return cleaned


class ChatMessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ("body",)
        widgets = {"body": forms.TextInput(attrs={"placeholder": "Ask about parking, balls, exact court..."})}


class SessionSearchForm(forms.Form):
    location = forms.CharField(
        required=False,
        label="Location",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Court, area, or postal code",
                "autocomplete": "off",
                "data-location-search": "true",
            }
        ),
    )
    radius_km = forms.DecimalField(
        required=False,
        label="Radius",
        help_text="Select a OneMap suggestion first if you want radius filtering.",
        min_value=Decimal("0.5"),
        max_value=Decimal("50"),
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"step": "0.5", "placeholder": "km"}),
    )
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())
    host = forms.CharField(required=False, label="Host", widget=forms.TextInput(attrs={"placeholder": "Host name"}))
    match_type = forms.ChoiceField(
        required=False,
        label="Type",
        choices=(("", "Any type"),) + tuple(PrataSession.MatchType.choices),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=(("", "Any status"),) + tuple(PrataSession.Status.choices),
    )
    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(attrs={"type": "date", "class": "date-input"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(attrs={"type": "date", "class": "date-input"}),
    )
    time_from = forms.TimeField(
        required=False,
        label="After",
        widget=forms.TimeInput(attrs={"type": "time", "class": "time-input"}),
    )
    time_to = forms.TimeField(
        required=False,
        label="Before",
        widget=forms.TimeInput(attrs={"type": "time", "class": "time-input"}),
    )

    def clean_latitude(self):
        return self._clean_coordinate("latitude")

    def clean_longitude(self):
        return self._clean_coordinate("longitude")

    def _clean_coordinate(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Choose a location from the search results.")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_to"] < cleaned["date_from"]:
            self.add_error("date_to", "End date must be after start date.")
        return cleaned


class MatchScoreForm(forms.Form):
    winner_side = forms.ChoiceField(
        label="Winner",
        choices=MatchResult.WinnerSide.choices,
        widget=forms.RadioSelect,
    )
    set1_host = forms.IntegerField(label="Set 1 host", min_value=0, max_value=7)
    set1_challenger = forms.IntegerField(label="Set 1 challenger", min_value=0, max_value=7)
    set2_host = forms.IntegerField(label="Set 2 host", min_value=0, max_value=7, required=False)
    set2_challenger = forms.IntegerField(label="Set 2 challenger", min_value=0, max_value=7, required=False)
    set3_host = forms.IntegerField(label="Set 3 host", min_value=0, max_value=10, required=False)
    set3_challenger = forms.IntegerField(label="Set 3 challenger", min_value=0, max_value=10, required=False)

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        if session:
            self.fields["winner_side"].choices = (
                (MatchResult.WinnerSide.HOST, session.host_side_name),
                (MatchResult.WinnerSide.CHALLENGER, session.challenger_side_name),
            )

    def clean(self):
        cleaned = super().clean()
        sets = []
        for index in range(1, 4):
            host_score = cleaned.get(f"set{index}_host")
            challenger_score = cleaned.get(f"set{index}_challenger")
            if host_score is None and challenger_score is None:
                continue
            if host_score is None or challenger_score is None:
                self.add_error(f"set{index}_host", "Enter both scores for this set.")
                continue
            if host_score == challenger_score:
                self.add_error(f"set{index}_host", "A set cannot be tied.")
                continue
            sets.append((index, host_score, challenger_score))
        if not sets:
            raise forms.ValidationError("Add at least one completed set.")
        host_sets = sum(1 for _, host, challenger in sets if host > challenger)
        challenger_sets = len(sets) - host_sets
        winner_side = cleaned.get("winner_side")
        if winner_side == MatchResult.WinnerSide.HOST and host_sets <= challenger_sets:
            self.add_error("winner_side", "Host side must win more sets than the challenger.")
        if winner_side == MatchResult.WinnerSide.CHALLENGER and challenger_sets <= host_sets:
            self.add_error("winner_side", "Challenger side must win more sets than the host.")
        cleaned["sets"] = sets
        return cleaned


class TestimonialForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(value, str(value)) for value in range(1, 6)],
        coerce=int,
        widget=forms.RadioSelect,
        label="Rating",
    )
    badges = forms.MultipleChoiceField(
        choices=TESTIMONIAL_BADGE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Choose up to 2 shoutouts",
        required=False,
    )

    class Meta:
        model = Testimonial
        fields = ("rating", "badges", "text")
        labels = {"text": "Optional note"}
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional: say what made them fun to play with."}),
        }

    def clean_rating(self):
        rating = self.cleaned_data["rating"]
        if rating < 1 or rating > 5:
            raise forms.ValidationError("Choose a rating from 1 to 5.")
        return rating

    def clean_badges(self):
        badges = self.cleaned_data["badges"]
        if len(badges) > 2:
            raise forms.ValidationError("Pick up to 2 shoutouts.")
        return badges

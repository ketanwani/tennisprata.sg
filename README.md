# tennisprata.sg POC

A Dockerized Django POC for social doubles tennis sessions with optional prata stakes.

## Stack

- Django web app
- Postgres database
- Redis broker
- Celery worker and Celery Beat for 24-hour reminders
- Responsive server-rendered HTML/CSS

## Run locally

```powershell
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Open [http://localhost:8000](http://localhost:8000).

Demo login:

```text
username: ketan
password: password
```

The demo `ketan` account is also staff/superuser, so it can access:

```text
http://localhost:8000/moderation/
http://localhost:8000/admin/
```

## POC Features

- User registration with email or phone and NTRP level
- Google login/signup wiring via django-allauth
- Singapore court search by name or postal code using OneMap
- Redis-backed caching for OneMap search results
- Editable user profile with avatar URL, home courts, reminders, match history
- Group-scoped prata sessions
- Reusable pairs and ad hoc pair names
- Join invite as solo, new pair, or existing pair
- Session detail page with player list, NTRP levels, invite link, weather risk, and result recording
- Session chat for parking, balls, exact court, delays, and prata planning
- Pair leaderboard from recorded wins
- Staff moderation dashboard for cancelling sessions, disabling users, and blocking emails/phone numbers
- Celery scheduled reminder scan for sessions starting in about 24 hours
- Console email/SMS/WhatsApp stubs plus calendar reminder log placeholder

## Production Notes

For a real deployment, replace the console reminder stubs with providers:

- Email: SES, Postmark, SendGrid, or SMTP
- SMS: Twilio, Vonage, or local Singapore SMS provider
- WhatsApp: WhatsApp Business Cloud API or Twilio WhatsApp
- Calendar invite: generate and attach `.ics` files to reminder emails

The app is already Postgres-backed in Docker. Set production `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS`, provider credentials, and run behind HTTPS.

## Google Login Setup

The code is wired for Google OAuth using django-allauth. To activate it:

1. Create an OAuth 2.0 Client ID in Google Cloud Console.
2. Add this redirect URI:

```text
http://localhost:8000/accounts/google/login/callback/
```

3. Add credentials to `.env.example` for the POC, or pass them directly:

```powershell
docker compose exec web python manage.py configure_google_oauth --client-id "..." --secret "..."
```

The command creates/updates the Django Site and Google SocialApp records.

For production, add the production callback URL too:

```text
https://tennisprata.sg/accounts/google/login/callback/
```

## Court Location Search

The create-session form uses OneMap for Singapore-first court search:

- Search by court/place name or Singapore postal code.
- Selected results fill play location, locality, address, postal code, latitude, and longitude.
- Session pages use saved latitude/longitude to generate a Google Maps navigation link.

For production, check OneMap attribution, API usage terms, and any production access requirements.

OneMap search responses are cached in Redis:

- Successful searches: 7 days
- Empty/error searches: 10 minutes
- Test by calling the same URL twice and checking `cache_status`:

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/locations/search/?q=Kallang" -UseBasicParsing
```

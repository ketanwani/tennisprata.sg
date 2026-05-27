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
Copy-Item .env.example .env
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

- Email-only user registration with verification and NTRP level
- Google login/signup wiring via django-allauth
- Singapore court search by name or postal code using OneMap
- Redis-backed caching for OneMap search results
- Editable user profile with validated photo upload, home courts, and match history
- Group-scoped prata sessions
- Reusable pairs and ad hoc pair names
- Join invite as solo, new pair, or existing pair
- Session detail page with player list, NTRP levels, invite link, weather risk, and result recording
- Session chat for parking, balls, exact court, delays, and prata planning
- Pair leaderboard from recorded wins
- Staff moderation dashboard for cancelling sessions, disabling users, and blocking emails
- Notification preferences for email reminders and calendar invites
- Celery scheduled email reminder scan for sessions starting in about 24 hours
- SMS and WhatsApp are shown as upcoming disabled channels

## Production Notes

For real email delivery, configure an SMTP or transactional email backend:

- Email: SES, Postmark, SendGrid, or SMTP
- Calendar invite: `.ics` files are attached to reminder emails when users enable calendar invites
- SMS and WhatsApp are intentionally disabled in the first version

The app is already Postgres-backed in Docker. Set production `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS`, provider credentials, and run behind HTTPS.

## DigitalOcean Deployment With Shared Nginx

The production stack uses Docker for Django/Postgres/Redis/Celery. A host-level Nginx instance handles public traffic for `tennisprata.live` and can also continue serving other websites on the same Droplet.

On the Droplet, clone the repository to:

```bash
/root/tennisprata.sg
```

Create `/root/tennisprata.sg/.env`:

```env
DEBUG=0
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=tennisprata.live,www.tennisprata.live,165.245.188.29,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://tennisprata.live,https://www.tennisprata.live
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
SECURE_SSL_REDIRECT=1
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=0
SECURE_HSTS_PRELOAD=0
ACCOUNT_EMAIL_VERIFICATION=mandatory
DATABASE_URL=postgres://tennisprata:tennisprata@db:5432/tennisprata
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
DJANGO_CACHE_URL=redis://redis:6379/2
DEFAULT_FROM_EMAIL=hello@tennisprata.live
APP_BASE_URL=https://tennisprata.live
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-smtp-user
EMAIL_HOST_PASSWORD=your-smtp-password
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ONEMAP_API_TOKEN=your-onemap-api-token
SITE_DOMAIN=tennisprata.live
```

Run the production Docker stack:

```bash
cd /root/tennisprata.sg
docker network create public-web || true
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput
```

Install Nginx and Certbot if they are not already installed:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

Add a new Nginx site for TennisPrata without removing your other sites:

```bash
sudo cp /root/tennisprata.sg/deploy/nginx/tennisprata.live.conf /etc/nginx/sites-available/tennisprata.live
sudo ln -s /etc/nginx/sites-available/tennisprata.live /etc/nginx/sites-enabled/tennisprata.live
sudo nginx -t
sudo systemctl reload nginx
```

Issue or update the HTTPS certificate:

```bash
sudo certbot --nginx -d tennisprata.live -d www.tennisprata.live
```

Allow web traffic if UFW is enabled:

```bash
sudo ufw allow 80
sudo ufw allow 443
```

After DNS points `tennisprata.live` and `www.tennisprata.live` to the Droplet IP, the site should be available at:

```text
https://tennisprata.live
```

The GitHub Actions workflow in `.github/workflows/deploy.yml` deploys with the same production compose command. It expects the repo to exist at `/root/tennisprata.sg` and the production `.env` file to stay on the Droplet.

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
https://tennisprata.live/accounts/google/login/callback/
```

Set these in `/root/tennisprata.sg/.env` on the Droplet:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
SITE_DOMAIN=tennisprata.live
```

GitHub Actions runs `configure_google_oauth` during deployment. If the Google credentials are blank, deployment continues and the Google buttons remain disabled.

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

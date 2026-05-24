import os

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Configure the Google OAuth SocialApp from environment variables or CLI options."

    def add_arguments(self, parser):
        parser.add_argument("--client-id", default=os.getenv("GOOGLE_CLIENT_ID", ""))
        parser.add_argument("--secret", default=os.getenv("GOOGLE_CLIENT_SECRET", ""))
        parser.add_argument("--domain", default=os.getenv("SITE_DOMAIN", "localhost:8000"))
        parser.add_argument("--name", default="Google")
        parser.add_argument("--skip-if-missing", action="store_true")

    def handle(self, *args, **options):
        client_id = options["client_id"].strip()
        secret = options["secret"].strip()
        domain = options["domain"].strip()
        if not client_id or not secret:
            if options["skip_if_missing"]:
                self.stdout.write(self.style.WARNING("Google OAuth credentials are not set; skipping SocialApp setup."))
                return
            raise CommandError("Provide GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or pass --client-id and --secret.")

        from allauth.socialaccount.models import SocialApp

        site, _ = Site.objects.update_or_create(
            id=1,
            defaults={"domain": domain, "name": domain},
        )
        app, _ = SocialApp.objects.update_or_create(
            provider="google",
            name=options["name"],
            defaults={"client_id": client_id, "secret": secret},
        )
        app.sites.add(site)
        self.stdout.write(self.style.SUCCESS(f"Configured Google OAuth for {domain}."))

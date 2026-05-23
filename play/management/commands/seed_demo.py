from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from play.models import GroupMembership, Pair, PlayGroup, PrataSession, Profile, SessionParticipant


class Command(BaseCommand):
    help = "Seed a small demo group with pairs and sessions."

    def handle(self, *args, **options):
        group, _ = PlayGroup.objects.get_or_create(
            slug="kallang-sunday-tennis",
            defaults={"name": "Kallang Sunday Tennis", "description": "Demo prata tennis group."},
        )
        players = []
        for username, name, level in [
            ("ketan", "Ketan Rao", "3.5"),
            ("aaron", "Aaron Lim", "4.0"),
            ("mira", "Mira Tan", "3.5"),
            ("sam", "Sam Ong", "3.5"),
        ]:
            user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
            if created:
                user.set_password("password")
                first, last = name.split(" ", 1)
                user.first_name = first
                user.last_name = last
            if username == "ketan":
                user.is_staff = True
                user.is_superuser = True
            user.save()
            Profile.objects.get_or_create(user=user, defaults={"ntrp_level": level, "home_courts": "Kallang"})
            GroupMembership.objects.get_or_create(group=group, user=user)
            players.append(user)

        host_pair, _ = Pair.objects.get_or_create(group=group, name="Ketan / Aaron", defaults={"is_regular": True})
        host_pair.players.set(players[:2])
        challenger_pair, _ = Pair.objects.get_or_create(group=group, name="Mira / Sam", defaults={"is_regular": True})
        challenger_pair.players.set(players[2:])

        session, _ = PrataSession.objects.get_or_create(
            group=group,
            title="Sunday prata decider",
            defaults={
                "host": players[0],
                "host_pair": host_pair,
                "challenger_pair": challenger_pair,
                "starts_at": timezone.now() + timezone.timedelta(days=2),
                "locality": "Kallang",
                "court_name": "ActiveSG Kallang Tennis Centre",
                "court_details": "Court 2, near the main gate",
                "cost_notes": "$14 court split",
                "weather_summary": "Partly cloudy",
                "weather_risk": "Low",
                "status": PrataSession.Status.CONFIRMED,
            },
        )
        for user in players[:2]:
            SessionParticipant.objects.get_or_create(
                session=session,
                user=user,
                defaults={"pair": host_pair, "side": SessionParticipant.Side.HOST},
            )
        for user in players[2:]:
            SessionParticipant.objects.get_or_create(
                session=session,
                user=user,
                defaults={"pair": challenger_pair, "side": SessionParticipant.Side.CHALLENGER},
            )

        self.stdout.write(self.style.SUCCESS("Seeded demo data. Login as ketan / password."))

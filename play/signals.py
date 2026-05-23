from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import GroupMembership, PlayGroup, Profile


@receiver(post_save, sender=User)
def create_profile_for_user(sender, instance, created, **kwargs):
    if not created:
        return
    Profile.objects.get_or_create(user=instance)
    group, _ = PlayGroup.objects.get_or_create(
        slug="kallang-sunday-tennis",
        defaults={"name": "Kallang Sunday Tennis", "description": "POC group for prata doubles challenges."},
    )
    GroupMembership.objects.get_or_create(group=group, user=instance)

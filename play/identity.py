from allauth.account.models import EmailAddress


def email_address_is_verified(user):
    if not user or not user.is_authenticated or not user.email:
        return False
    return EmailAddress.objects.filter(
        user=user,
        email__iexact=user.email,
        verified=True,
    ).exists()


def create_unverified_primary_email(user):
    if not user.email:
        return None
    email_address, _ = EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)
    return email_address

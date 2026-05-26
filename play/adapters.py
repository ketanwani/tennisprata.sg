import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .models import BlockedIdentity, normalize_identity

logger = logging.getLogger(__name__)


class TennisPrataAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        next_invite = request.session.pop("next_invite", None)
        next_pair_invite = request.session.pop("next_pair_invite", None)
        return next_invite or next_pair_invite or super().get_login_redirect_url(request)


class TennisPrataSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        for email in self._social_login_emails(sociallogin):
            if BlockedIdentity.objects.filter(
                identity_type=BlockedIdentity.IdentityType.EMAIL,
                value=normalize_identity(BlockedIdentity.IdentityType.EMAIL, email),
            ).exists():
                logger.warning("Blocked Google OAuth attempt for email=%s", email)
                messages.error(
                    request,
                    "This Google account is not allowed to log in to tennisprata.sg.",
                    extra_tags="oauth",
                )
                raise ImmediateHttpResponse(redirect("login"))

    def _social_login_emails(self, sociallogin):
        emails = []
        for email_address in sociallogin.email_addresses:
            if email_address.email:
                emails.append(email_address.email)
        if getattr(sociallogin.user, "email", ""):
            emails.append(sociallogin.user.email)
        provider_email = sociallogin.account.extra_data.get("email") if sociallogin.account else ""
        if provider_email:
            emails.append(provider_email)
        return {email.strip().lower() for email in emails if email}

    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ):
        logger.error(
            "Google OAuth failed. provider=%s error=%s exception=%r extra_context=%s",
            getattr(provider, "id", provider),
            error,
            exception,
            extra_context,
            exc_info=exception if exception else None,
        )
        messages.error(
            request,
            "Google sign-in could not be completed. Please try again or use email/phone login.",
            extra_tags="oauth",
        )
        raise ImmediateHttpResponse(redirect("login"))

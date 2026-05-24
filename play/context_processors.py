def oauth_status(request):
    try:
        from allauth.socialaccount.models import SocialApp

        google_oauth_enabled = SocialApp.objects.filter(provider="google").exclude(client_id="").exists()
    except Exception:
        google_oauth_enabled = False
    return {"google_oauth_enabled": google_oauth_enabled}

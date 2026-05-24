from allauth.account.adapter import DefaultAccountAdapter


class TennisPrataAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        next_invite = request.session.pop("next_invite", None)
        next_pair_invite = request.session.pop("next_pair_invite", None)
        return next_invite or next_pair_invite or super().get_login_redirect_url(request)

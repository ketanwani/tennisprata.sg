from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.TennisPrataLoginView.as_view(), name="login"),
    path("logout/", views.TennisPrataLogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("my-sessions/", views.my_sessions, name="my_sessions"),
    path("pairs/new/", views.create_pair, name="create_pair"),
    path("pairs/<int:pk>/", views.pair_detail, name="pair_detail"),
    path("pairs/<int:pk>/leave/", views.leave_pair, name="leave_pair"),
    path("pairs/<int:pk>/invite/", views.update_pair_invite, name="update_pair_invite"),
    path("pairs/<int:pk>/accepted/", views.pair_invite_accepted, name="pair_invite_accepted"),
    path("pairs/accept/<str:invite_code>/", views.accept_pair_invite, name="accept_pair_invite"),
    path("sessions/new/", views.create_session, name="create_session"),
    path("locations/search/", views.location_search, name="location_search"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/accepted/", views.session_invite_accepted, name="session_invite_accepted"),
    path("sessions/<int:pk>/edit/", views.edit_session, name="edit_session"),
    path("sessions/<int:pk>/cancel/", views.cancel_session, name="cancel_session"),
    path("sessions/<int:pk>/withdraw/", views.withdraw_session, name="withdraw_session"),
    path("i/<str:invite_code>/", views.join_invite, name="join_invite"),
    path("moderation/", views.moderation_dashboard, name="moderation_dashboard"),
    path("moderation/sessions/<int:pk>/cancel/", views.moderation_cancel_session, name="moderation_cancel_session"),
    path("moderation/users/<int:user_id>/disable/", views.moderation_disable_user, name="moderation_disable_user"),
    path("moderation/blocked/<int:pk>/unblock/", views.moderation_unblock_identity, name="moderation_unblock_identity"),
]

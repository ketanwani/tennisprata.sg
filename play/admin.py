from django.contrib import admin

from .models import (
    ChatMessage,
    GroupMembership,
    MatchResult,
    MatchSetScore,
    Notification,
    Pair,
    PlayGroup,
    PrataSession,
    Profile,
    ReminderLog,
    SessionParticipant,
    SessionPhoto,
    Testimonial,
    BlockedIdentity,
)

admin.site.register(Profile)
admin.site.register(PlayGroup)
admin.site.register(GroupMembership)
admin.site.register(Pair)
admin.site.register(PrataSession)
admin.site.register(SessionParticipant)
admin.site.register(ChatMessage)
admin.site.register(MatchResult)
admin.site.register(MatchSetScore)
admin.site.register(ReminderLog)
admin.site.register(BlockedIdentity)
admin.site.register(Notification)
admin.site.register(SessionPhoto)
admin.site.register(Testimonial)

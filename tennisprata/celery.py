import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tennisprata.settings")

app = Celery("tennisprata")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

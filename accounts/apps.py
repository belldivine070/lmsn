from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_in


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        import core.signals

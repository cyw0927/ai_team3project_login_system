from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = "dashboard"

    def ready(self):
        from .upload_policy import register_model_upload_validation

        register_model_upload_validation()

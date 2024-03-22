from django.db import models


class BaseConstraint(models.BaseConstraint):
    def get_violation_error_message(self):
        if isinstance(self.violation_error_message, dict):
            return self.violation_error_message

        return super().get_violation_error_message()

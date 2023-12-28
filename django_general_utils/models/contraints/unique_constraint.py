from django.db.models import UniqueConstraint as BaseUniqueConstraint


class UniqueConstraint(BaseUniqueConstraint):
    def get_violation_error_message(self):
        if self.violation_error_message is not None:
            return self.violation_error_message

        return super().get_violation_error_message()

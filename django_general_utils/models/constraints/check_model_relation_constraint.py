from django.core.exceptions import ValidationError
from django.db.utils import DEFAULT_DB_ALIAS
from django.utils.translation import gettext_lazy as _
from safedelete.config import FIELD_NAME
from django_general_utils.models.constraints import BaseConstraint


class CheckModelRelationConstraint(BaseConstraint):
    def __init__(
            self,
            name,
            check = None,
            validate_on_create=True,
            validate_on_update=True,
            validate_on_delete=False,
            violation_error_message=None
    ):
        self.check = check
        self.validate_on_create = validate_on_create
        self.validate_on_update = validate_on_update
        self.validate_on_delete = validate_on_delete

        super().__init__(name=name, violation_error_message=violation_error_message)

    def _get_check_sql(self, model, schema_editor):
        return None

    def constraint_sql(self, model, schema_editor):
        return None

    def create_sql(self, model, schema_editor):
        return None

    def remove_sql(self, model, schema_editor):
        return None

    def validate(self, model, instance, exclude=None, using=DEFAULT_DB_ALIAS):
        """
        Validate the constraint
        @return:
        """
        if self.validate_on_delete and getattr(instance, FIELD_NAME, None) is not None:
            return None

        assert self.check is not None, _('Check must be defined')

        if not self.validate_on_create and instance._state.adding:
            return None

        if not self.validate_on_update and not instance._state.adding:
            return None

        check_result = self.check(instance)

        if isinstance(check_result, (str, dict)):
            raise ValidationError(check_result)

        if check_result is None or (isinstance(check_result, bool) and check_result):
            raise ValidationError(self.get_violation_error_message())

        return None

    def __eq__(self, other):
        if isinstance(other, CheckModelRelationConstraint):
            return (
                    self.check == other.check
                    and self.validate_on_create == other.validate_on_create
                    and self.validate_on_update == other.validate_on_update
                    and self.validate_on_delete == other.validate_on_delete
                    and self.violation_error_message == other.violation_error_message
            )
        return super().__eq__(other)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()

        kwargs.update({
            'check': self.check,
            'validate_on_create': self.validate_on_create,
            'validate_on_update': self.validate_on_update,
            'validate_on_delete': self.validate_on_delete,
        })

        return path, args, kwargs

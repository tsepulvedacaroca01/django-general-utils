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
        # Stored as `check_func`, not `check` — `check` is a method name reserved by
        # `django.db.models.BaseConstraint.check(model, connection)` (Django's own system
        # check hook, called by `Model.check()`/`_check_constraints`). Naming this attribute
        # `check` shadows that inherited method with our validation callable, so Django ends
        # up calling e.g. `validate_client_flow_flags(model, connection)` instead of the real
        # system check, raising a TypeError. The public `check=` kwarg is kept unchanged so
        # existing migrations that pass `check=...` keep working.
        self.check_func = check
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

        assert self.check_func is not None, _('Check must be defined')

        if not self.validate_on_create and instance._state.adding:
            return None

        if not self.validate_on_update and not instance._state.adding:
            return None

        check_result = self.check_func(instance)

        if isinstance(check_result, (str, dict)):
            raise ValidationError(check_result)

        if check_result is None or (isinstance(check_result, bool) and check_result):
            raise ValidationError(self.get_violation_error_message())

        return None

    def __eq__(self, other):
        if isinstance(other, CheckModelRelationConstraint):
            return (
                    self.check_func == other.check_func
                    and self.validate_on_create == other.validate_on_create
                    and self.validate_on_update == other.validate_on_update
                    and self.validate_on_delete == other.validate_on_delete
                    and self.violation_error_message == other.violation_error_message
            )
        return super().__eq__(other)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()

        kwargs.update({
            'check': self.check_func,
            'validate_on_create': self.validate_on_create,
            'validate_on_update': self.validate_on_update,
            'validate_on_delete': self.validate_on_delete,
        })

        return path, args, kwargs

from django.core.exceptions import ValidationError
from django.db.utils import DEFAULT_DB_ALIAS
from django.utils.translation import gettext_lazy as _

from django_general_utils.models.constraints import BaseConstraint


class CheckFlowStatusConstraint(BaseConstraint):
    def __init__(
            self,
            name,
            flow: dict, # {'P': ['E', 'C'], 'E': ['F', 'C'], 'F': ['C'], 'C': [], 'CE': []}
            field = 'status',
            initial_statuses = None,
            validate_on_create=True,
            validate_on_update=True,
            skip_validate=None,
            violation_error_message=None,
            violation_error_initial_statuses_message=None
    ):
        self.field = field
        self.flow = flow
        self.initial_statuses = initial_statuses
        self.validate_on_create = validate_on_create
        self.validate_on_update = validate_on_update
        self.skip_validate = skip_validate
        self.violation_error_message = violation_error_message
        self.violation_error_initial_statuses_message = violation_error_initial_statuses_message

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
        assert hasattr(instance, 'tracker'), _('The instance must have the "tracker" field')

        # If the field has not changed, return None
        if not instance.tracker.has_changed(self.field):
            return None

        # If the instance is being created and the validation is not required, return None
        if not self.validate_on_create and instance._state.adding:
            return None

        current_value = getattr(instance, self.field)
        last_value = instance.tracker.previous(self.field)
        choices = dict(model._meta.get_field(self.field).choices)

        if self.skip_validate is not None and self.skip_validate(instance, last_value, current_value):
            return None

        # If the instance is being created and the initial statuses are defined, validate that the current value is in the initial statuses
        if (
                self.validate_on_create
                and instance._state.adding
                and isinstance(self.initial_statuses, list)
                and current_value not in self.initial_statuses
        ):
            violation_error_initial_statuses_message = self.violation_error_initial_statuses_message or {
                'status': _(f'El flujo inicial del modelo {model.__name__} y el campo {self.field} debe ser uno de los siguientes: %s' % ', '.join(self.initial_statuses))
            }
            message = {
                _key: _value.format(
                    current_value=current_value,
                    current_value_display=choices.get(current_value)
                )
                for _key, _value in violation_error_initial_statuses_message.items()
            }
            raise ValidationError(message)

        # If the instance is being updated and the validation is not required, return None
        if not self.validate_on_update and not instance._state.adding:
            return None

        # If the instance is being created and the last value is None, return None
        if last_value is None and instance._state.adding:
            return None

            # If the las value is None and the instance is not being created, return None
        if last_value is None and not instance._state.adding:
            return None

        # If the last value is equal to the current value, return None
        if last_value == current_value:
            return None

        # If the current value is not in the flow of the last value, raise a validation error
        if current_value not in self.flow.get(last_value, []):
            violation_error_initial_statuses_message = self.violation_error_initial_statuses_message or {
                'status': 'No puedes avanzar este estado a "{current_value}" debido a que su valor actual "{last_value}" no lo permite.',
            }
            message = {
                _key: _value.format(
                    current_value=current_value,
                    last_value=last_value,
                )
                for _key, _value in violation_error_initial_statuses_message.items()
            }

            raise ValidationError(message)

        return None

    def __eq__(self, other):
        if isinstance(other, CheckFlowStatusConstraint):
            return (
                    self.field == other.field
                    and self.flow == other.flow
                    and self.initial_statuses == other.initial_statuses
                    and self.validate_on_create == other.validate_on_create
                    and self.validate_on_update == other.validate_on_update
                    and self.skip_validate == other.skip_validate
                    and self.violation_error_message == other.violation_error_message
                    and self.violation_error_initial_statuses_message == other.violation_error_initial_statuses_message
            )
        return super().__eq__(other)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()

        kwargs.update({
            'field': self.field,
            'flow': self.flow,
            'initial_statuses': self.initial_statuses,
            'validate_on_create': self.validate_on_create,
            'validate_on_update': self.validate_on_update,
            'skip_validate': self.skip_validate,
            'violation_error_message': self.violation_error_message,
            'violation_error_initial_statuses_message': self.violation_error_initial_statuses_message,
        })

        return path, args, kwargs

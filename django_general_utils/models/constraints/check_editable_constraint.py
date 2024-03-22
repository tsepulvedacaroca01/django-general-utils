from django.core.exceptions import ValidationError
from django.db.utils import DEFAULT_DB_ALIAS
from django.utils.translation import gettext_lazy as _

from django_general_utils.models.constraints import BaseConstraint


class CheckEditableConstraint(BaseConstraint):
    def __init__(
            self,
            name,
            fields: list = None,
            violation_error_message=None
    ):
        self.fields = fields or []

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
        assert len(self.fields) > 0, _('The fields must be defined')
        assert hasattr(instance, 'tracker'), _('The instance must have the "tracker" field')

        # If the instance is being created and the validation is not required, return None
        if instance._state.adding:
            return None

        errors = {}

        for _field in self.fields:
            if instance.tracker.has_changed(_field):
                errors[_field] = _(f'El campo {_field} no es editable')

        if len(errors) > 0:
            raise ValidationError(errors)

        return None

    def __eq__(self, other):
        if isinstance(other, CheckModelRelationConstraint):
            return (
                    self.fields == other.fields
            )
        return super().__eq__(other)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()

        kwargs.update({
            'fields': self.fields,
        })

        return path, args, kwargs

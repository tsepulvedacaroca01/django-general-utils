from django.core.exceptions import ValidationError, FieldError
from django.db.models import Q
from django.db.utils import DEFAULT_DB_ALIAS
from django.utils.translation import gettext_lazy as _
from safedelete.config import FIELD_NAME

from django_general_utils.models.constraints import BaseConstraint


class CheckRowsModelWithoutSafeDeleteConstraint(BaseConstraint):
    def __init__(
            self,
            max_rows: int,
            name,
            check=None,
            violation_error_message=None
    ):
        self.max_rows = max_rows
        self.check = check

        if check is not None and not getattr(check, "conditional", False):
            raise TypeError(
                _("CheckConstraint.check must be a Q instance or boolean expression.")
            )

        if max_rows < 1:
            raise TypeError(
                _('El número máximo de filas debe ser mayor a 0.')
            )

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
        # Django < 5.0
        if hasattr(instance, '_get_field_value_map') and callable(getattr(instance, '_get_field_value_map')):
            against = instance._get_field_value_map(meta=model._meta, exclude=exclude)
        elif hasattr(instance, '_get_field_expression_map') and callable(getattr(instance, '_get_field_expression_map')):
            against = instance._get_field_expression_map(meta=model._meta, exclude=exclude)
        else:
            raise ValueError('instance must have a method "_get_field_value_map" or "_get_field_expression_map"')
        try:
            if not Q(self.check).check(against, using=using):
                return  # Skip validation if the check is not applicable
        except FieldError:
            pass

        queryset = model._default_manager.using(using)
        model_class_pk = instance._get_pk_val(model._meta)

        # Check if the model has a custom manager that filters out some rows
        if self.check is not None:
            queryset = queryset.filter(self.check)

        # Check if the model is being updated
        if not instance._state.adding and model_class_pk is not None:
            queryset = queryset.exclude(pk=model_class_pk)

        if queryset.count() >= self.max_rows:
            raise ValidationError(self.get_violation_error_message())

    def __eq__(self, other):
        if isinstance(other, CheckRowsModelWithoutSafeDeleteConstraint):
            return (
                    self.max_rows == other.max_rows
                    and self.name == other.name
                    and self.check == other.check
                    and self.violation_error_message == other.violation_error_message
            )
        return super().__eq__(other)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()
        kwargs.update({
            'max_rows': self.max_rows,
            'check': self.check,
        })

        return path, args, kwargs

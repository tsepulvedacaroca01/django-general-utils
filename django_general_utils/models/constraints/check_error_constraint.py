from django.core.exceptions import FieldError, ValidationError
from django.db import models
from django.db.models.query_utils import Q
from django.db.utils import DEFAULT_DB_ALIAS
from django.db.models.sql.query import Query
from .base_constraint import BaseConstraint


class CheckErrorConstraint(BaseConstraint, models.CheckConstraint):
    def _get_check_sql(self, model, schema_editor):
        query = Query(model=model, alias_cols=False)
        where = query.build_where(~self.check)
        compiler = query.get_compiler(connection=schema_editor.connection)
        sql, params = where.as_sql(compiler, schema_editor.connection)
        return sql % tuple(schema_editor.quote_value(p) for p in params)

    def validate(self, model, instance, exclude=None, using=DEFAULT_DB_ALIAS):
        # Django < 5.0
        if hasattr(instance, '_get_field_value_map') and callable(getattr(instance, '_get_field_value_map')):
            against = instance._get_field_value_map(meta=model._meta, exclude=exclude)
        elif hasattr(instance, '_get_field_expression_map') and callable(getattr(instance, '_get_field_expression_map')):
            against = instance._get_field_expression_map(meta=model._meta, exclude=exclude)
        else:
            raise ValueError('instance must have a method "_get_field_value_map" or "_get_field_expression_map"')

        try:
            if Q(self.check).check(against, using=using):
                raise ValidationError(
                    self.get_violation_error_message(), code=self.violation_error_code
                )
        except FieldError:
            pass

from django.db import models
from safedelete.config import FIELD_NAME

from .base_constraint import BaseConstraint


class UniqueConstraint(BaseConstraint, models.UniqueConstraint):
    def __init__(
            self,
            prefix=None,
            include_deleted=False,
            fields=(),
            condition=None,
            name=None,
            *args,
            **kwargs
    ):
        if not include_deleted:
            deleted_filter = {f'{FIELD_NAME}__isnull': True}
            deleted_condition = models.Q(**deleted_filter)

            if condition is None:
                condition = deleted_condition
            elif f'{FIELD_NAME}__isnull' not in [_child[0] for _child in condition.children if isinstance(_child, tuple)]:
                condition = deleted_condition & condition

        if name is None:
            name = '{prefix}unique{active}_{fields}'.format(
                prefix=f'{prefix}_' if prefix is not None else '',
                active='_active' if not include_deleted else '',
                fields='_'.join(fields),
            )

        super().__init__(condition=condition, fields=fields, name=name, *args, **kwargs)

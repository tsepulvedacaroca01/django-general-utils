from django.db import models
from safedelete.config import FIELD_NAME

from .base_constraint import BaseConstraint


class UniqueWithoutSafeDeleteConstraint(BaseConstraint, models.UniqueConstraint):
    def __init__(
            self,
            prefix=None,
            fields=(),
            condition=None,
            name=None,
            *args,
            **kwargs
    ):
        if name is None:
            name = '{prefix}unique_active_{fields}'.format(
                prefix=f'{prefix}_' if prefix is not None else '',
                fields='_'.join(fields),
            )

        super().__init__(condition=condition, fields=fields, name=name, *args, **kwargs)

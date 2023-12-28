from typing import Union
from uuid import UUID

from django.utils.translation import gettext_lazy as _


def ids_in_query(ids: list[Union[int, UUID]], ids_available: list[int], error: str = _('Not found.')) -> list:
    """
    validates if the id is in the list, if not, it inserts an error
    @param ids: Ids to validate
    @param ids_available: Ids Available
    @param error: Default message error
    @return: errors list
    """
    errors = []

    if len(ids) != len(ids_available):
        for _id in ids:
            if _id not in ids_available:
                errors.append([error])
            else:
                errors.append([])
    return errors

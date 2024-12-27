import re

from django.db.models import Func


class ArrayAppend(Func):
    function = 'array_cat'

    def __init__(self, field, elements: list, *args, **kwargs):
        """
        Agrega elementos a un array
        @param field: campo
        @param elements: elementos a agregar al array
        """
        super().__init__(field, elements, *args, **kwargs)

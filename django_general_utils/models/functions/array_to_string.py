from django.db.models import Func, Value, CharField

class ArrayToString(Func):
    function = 'array_to_string'
    output_field = CharField()

    def __init__(self, array_field, delimiter, null_value='', **extra):
        """
        Transforma un ArrayField en un String usando un delimitador.
        """
        expressions = [
            array_field,
            Value(delimiter),
            Value(null_value),
        ]
        super().__init__(*expressions, **extra)

from django.db.models import Func, FloatField


class Round(Func):
    function = 'ROUND'
    arity = 2
    output_field = FloatField()

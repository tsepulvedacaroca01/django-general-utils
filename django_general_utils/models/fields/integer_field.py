from django.db import models

from .formated_number_field import FormattedNumberField


class IntegerField(FormattedNumberField, models.IntegerField):
    pass

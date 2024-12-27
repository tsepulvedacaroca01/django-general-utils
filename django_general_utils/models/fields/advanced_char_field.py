from django.db import models
from django.utils.translation import gettext_lazy as _


class AdvancedCharField(models.CharField):
    def __init__(self, *args, **kwargs):
        self.to_upper = kwargs.pop('to_upper', False)
        self.to_lower = kwargs.pop('to_lower', False)
        self.to_title = kwargs.pop('to_title', False)

        self.left_strip = kwargs.pop('left_strip', False)
        self.right_strip = kwargs.pop('right_strip', False)
        self.strip = kwargs.pop('strip', False)

        assert self.to_upper + self.to_lower + self.to_title <= 1, _("Only one of to_upper, to_lower, or to_title can be True")

        # You can add any custom initialization logic here
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        if value is None:
            return super().get_prep_value(value)

        if not isinstance(value, str):
            return super().get_prep_value(value)

        if self.to_upper:
            value = value.upper()
        elif self.to_lower:
            value = value.lower()
        elif self.to_title:
            value = value.title()

        if self.left_strip:
            value = value.lstrip()
        if self.right_strip:
            value = value.rstrip()
        if self.strip:
            value = value.strip()

        return super().get_prep_value(value)

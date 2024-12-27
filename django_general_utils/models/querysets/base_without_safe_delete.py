from django.core.exceptions import ValidationError
from ordered_model.models import OrderedModelQuerySet

from ...utils.drf.validation_errors import ListValidationError


class BaseModelWithoutSafeDeleteQuerySet(OrderedModelQuerySet):
    def active(self):
        """ Return only active records"""
        return self.filter(is_active=True)

    def bulk_create(self, objs, *args, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            errors = []

            for _obj in objs:
                try:
                    _obj.full_clean()
                    errors.append(ValidationError({}))
                except ValidationError as e:
                    errors.append(e)

            if any([len(_error.message_dict) > 0 for _error in errors]):
                raise ListValidationError(errors)

        response = super().bulk_create(objs, *args, **kwargs)

        return response

    def bulk_update(self, objs, *args, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            errors = []

            for _obj in objs:
                try:
                    _obj.full_clean()
                    errors.append(ValidationError({}))
                except ValidationError as e:
                    errors.append(e)

            if any([len(_error.message_dict) > 0 for _error in errors]):
                raise ListValidationError(errors)

        response = super().bulk_update(objs, *args, **kwargs)

        return response

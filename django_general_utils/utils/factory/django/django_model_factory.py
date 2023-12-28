import factory.fuzzy
from django.db import IntegrityError

from django_general_utils.utils.factory import to_dict


class DjangoModelFactory(factory.django.DjangoModelFactory):
    @classmethod
    def to_dict(cls, fields: list = None, exclude: list = None):
        return to_dict(cls, fields, exclude)

    @classmethod
    def _get_or_create(cls, model_class, *args, **kwargs):
        """Create an instance of the model through objects.get_or_create."""
        manager = cls._get_manager(model_class)

        assert 'defaults' not in cls._meta.django_get_or_create, (
                "'defaults' is a reserved keyword for get_or_create "
                "(in %s._meta.django_get_or_create=%r)"
                % (cls, cls._meta.django_get_or_create))

        key_fields = {}
        for field in cls._meta.django_get_or_create:
            if field not in kwargs:
                raise factory.errors.FactoryError(
                    "django_get_or_create - "
                    "Unable to find initialization value for '%s' in factory %s" %
                    (field, cls.__name__))
            key_fields[field] = kwargs.pop(field)
        key_fields['defaults'] = kwargs

        try:
            # EDIT
            # instance, _created = manager.get_or_create(*args, **key_fields)
            defaults = key_fields.pop('defaults', {})
            instance = manager.create(*args, **key_fields, **defaults)
        except IntegrityError as e:

            if cls._original_params is None:
                raise e

            get_or_create_params = {
                lookup: value
                for lookup, value in cls._original_params.items()
                if lookup in cls._meta.django_get_or_create
            }
            if get_or_create_params:
                try:
                    instance = manager.get(**get_or_create_params)
                except manager.model.DoesNotExist:
                    # Original params are not a valid lookup and triggered a create(),
                    # that resulted in an IntegrityError. Follow Django’s behavior.
                    raise e
            else:
                raise e

        return instance

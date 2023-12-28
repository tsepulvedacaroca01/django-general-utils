import factory.fuzzy

from django_general_utils.utils.factory import to_dict


class DjangoModelFactory(factory.django.DjangoModelFactory):
    @classmethod
    def to_dict(cls, fields: list = None, exclude: list = None):
        return to_dict(cls, fields, exclude)

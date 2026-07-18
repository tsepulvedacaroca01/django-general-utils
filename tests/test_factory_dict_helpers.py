import unittest
from datetime import date, datetime, time

import django
import factory
from django.conf import settings

if not settings.configured:
    import os

    settings.configure(
        BASE_DIR=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'django_general_utils')),
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=(
            'django.contrib.auth',
            'django.contrib.contenttypes',
        ),
        TIME_ZONE='UTC',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.AutoField',
    )
    django.setup()

from django_general_utils.utils.factory import generate_dict_factory, to_dict


class _Person:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class PersonFactory(factory.Factory):
    class Meta:
        model = _Person

    name = 'John'
    age = 30
    birthday = date(1990, 1, 1)
    registered_at = datetime(2024, 1, 1, 12, 30, 45)
    login_time = time(8, 30, 0)


class GenerateDictFactoryTests(unittest.TestCase):
    def test_returns_plain_values_as_is(self):
        result = generate_dict_factory(PersonFactory)()

        self.assertEqual(result['name'], 'John')
        self.assertEqual(result['age'], 30)

    def test_datetime_is_formatted_as_string(self):
        result = generate_dict_factory(PersonFactory)()

        self.assertEqual(result['registered_at'], '2024-01-01 12:30:45')

    def test_date_is_formatted_as_string(self):
        result = generate_dict_factory(PersonFactory)()

        self.assertEqual(result['birthday'], '1990-01-01')

    def test_time_is_formatted_as_string(self):
        result = generate_dict_factory(PersonFactory)()

        self.assertEqual(result['login_time'], '08:30:00')

    def test_overrides_are_applied(self):
        result = generate_dict_factory(PersonFactory)(name='Jane')

        self.assertEqual(result['name'], 'Jane')

    def test_does_not_hit_the_database(self):
        # .stub() never calls Model.objects.create(), so this must not raise
        # even though no DB/table exists for _Person.
        generate_dict_factory(PersonFactory)()


class ToDictTests(unittest.TestCase):
    def test_no_filters_returns_full_dict(self):
        result = to_dict(PersonFactory)

        self.assertIn('name', result)
        self.assertIn('age', result)

    def test_fields_include_only_listed_keys(self):
        result = to_dict(PersonFactory, fields=['name'])

        self.assertEqual(result, {'name': 'John'})

    def test_exclude_removes_listed_keys(self):
        result = to_dict(PersonFactory, exclude=['name', 'age', 'birthday', 'registered_at', 'login_time'])

        self.assertEqual(result, {})

    def test_fields_and_exclude_together_exclude_wins(self):
        result = to_dict(PersonFactory, fields=['name', 'age'], exclude=['name'])

        self.assertEqual(result, {'age': 30})

    def test_unknown_keys_are_silently_ignored(self):
        result = to_dict(PersonFactory, fields=['does_not_exist'])

        self.assertEqual(result, {})


if __name__ == '__main__':
    unittest.main()

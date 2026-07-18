import unittest

import django
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

from django_general_utils.utils.drf.json_to_form_data import json_to_form_data


class JsonToFormDataTests(unittest.TestCase):
    def test_empty_dict(self):
        self.assertEqual(json_to_form_data({}), {})

    def test_flat_dict(self):
        self.assertEqual(
            json_to_form_data({'name': 'Acme', 'active': True}),
            {'name': 'Acme', 'active': True},
        )

    def test_nested_dict_levels_are_dot_joined(self):
        result = json_to_form_data({'parent': {'child': 'value'}})

        self.assertEqual(result, {'parent.child': 'value'})

    def test_three_levels_of_nested_dicts(self):
        result = json_to_form_data({'a': {'b': {'c': 'value'}}})

        self.assertEqual(result, {'a.b.c': 'value'})

    def test_list_of_scalars_uses_bracket_index(self):
        result = json_to_form_data({'tags': ['a', 'b']})

        self.assertEqual(result, {'tags[0]': 'a', 'tags[1]': 'b'})

    def test_list_of_dicts(self):
        # A dict directly following a list level still inherits the "dict"
        # marker from the enclosing dict (the list doesn't reset it), so it
        # gets the "." separator too: "items[0].name", not "items[0]name".
        result = json_to_form_data({'items': [{'name': 'x'}, {'name': 'y'}]})

        self.assertEqual(result, {'items[0].name': 'x', 'items[1].name': 'y'})

    def test_custom_separator(self):
        result = json_to_form_data({'tags': ['a', 'b']}, sep='.{i}.')

        self.assertEqual(result, {'tags.0.': 'a', 'tags.1.': 'b'})

    def test_falsy_leaf_values_are_preserved(self):
        result = json_to_form_data({'a': None, 'b': False, 'c': 0, 'd': ''})

        self.assertEqual(result, {'a': None, 'b': False, 'c': 0, 'd': ''})

    def test_top_level_list_input(self):
        result = json_to_form_data(['a', 'b'])

        self.assertEqual(result, {'[0]': 'a', '[1]': 'b'})


if __name__ == '__main__':
    unittest.main()

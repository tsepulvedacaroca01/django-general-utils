import json
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

from django_general_utils.utils.str_to_boolean import str_to_boolean


class StrToBooleanTests(unittest.TestCase):
    def test_true_literal(self):
        self.assertIs(str_to_boolean('true'), True)

    def test_false_literal(self):
        self.assertIs(str_to_boolean('false'), False)

    def test_case_insensitive(self):
        self.assertIs(str_to_boolean('TRUE'), True)

    def test_null_literal_returns_none(self):
        self.assertIsNone(str_to_boolean('null'))

    def test_numeric_string_returns_int_not_bool(self):
        result = str_to_boolean('1')

        self.assertEqual(result, 1)
        self.assertNotIsInstance(result, bool)

    def test_float_string_returns_float(self):
        self.assertEqual(str_to_boolean('1.5'), 1.5)

    def test_quoted_string_returns_string(self):
        self.assertEqual(str_to_boolean('"foo"'), 'foo')

    def test_non_str_input_passthrough_int(self):
        self.assertEqual(str_to_boolean(5), 5)

    def test_non_str_input_passthrough_none(self):
        self.assertIsNone(str_to_boolean(None))

    def test_non_str_input_passthrough_list(self):
        self.assertEqual(str_to_boolean([1, 2]), [1, 2])

    def test_invalid_literal_raises_by_default(self):
        with self.assertRaises(json.decoder.JSONDecodeError):
            str_to_boolean('foo')

    def test_invalid_literal_with_return_value_true_returns_original(self):
        self.assertEqual(str_to_boolean('foo', return_value=True), 'foo')

    def test_empty_string_raises_by_default(self):
        with self.assertRaises(json.decoder.JSONDecodeError):
            str_to_boolean('')

    def test_empty_string_with_return_value_true(self):
        self.assertEqual(str_to_boolean('', return_value=True), '')


if __name__ == '__main__':
    unittest.main()

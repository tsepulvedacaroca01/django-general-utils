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

from django_general_utils.utils.drf.validations.ids_in_query import ids_in_query
from django_general_utils.utils.drf.validations.unique_fields import unique_fields


class IdsInQueryTests(unittest.TestCase):
    def test_different_length_flags_missing_ids(self):
        # ids_available has fewer entries than ids -> lengths differ -> the
        # membership loop actually runs.
        result = ids_in_query([1, 2], [1])

        self.assertEqual(result, [[], ['Not found.']])

    def test_different_length_all_present(self):
        result = ids_in_query([1], [1, 2])

        self.assertEqual(result, [[]])

    def test_same_length_with_zero_overlap_returns_no_errors(self):
        # Known bug: the membership check is only performed when the two
        # lists have different lengths. Same-length lists short-circuit to
        # "no errors" even when nothing actually matches.
        result = ids_in_query([1, 2], [3, 4])

        self.assertEqual(result, [])

    def test_both_empty_returns_no_errors(self):
        self.assertEqual(ids_in_query([], []), [])

    def test_custom_error_message(self):
        result = ids_in_query([1, 2], [1], error='custom error')

        self.assertEqual(result, [[], ['custom error']])


class UniqueFieldsTests(unittest.TestCase):
    def test_no_duplicates(self):
        values = [{'email': 'a@x.com'}, {'email': 'b@x.com'}]

        with_error, errors = unique_fields(values, ['email'])

        self.assertFalse(with_error)
        self.assertEqual(errors, [[], []])

    def test_duplicate_field_flags_both_rows_as_list(self):
        values = [{'email': 'a@x.com'}, {'email': 'a@x.com'}, {'email': 'b@x.com'}]

        with_error, errors = unique_fields(values, ['email'])

        self.assertTrue(with_error)
        self.assertEqual(errors, [['This field cannot be repeated.'], ['This field cannot be repeated.'], []])

    def test_duplicate_field_with_key_true_returns_dicts(self):
        values = [{'email': 'a@x.com'}, {'email': 'a@x.com'}]

        with_error, errors = unique_fields(values, ['email'], with_key=True)

        self.assertTrue(with_error)
        self.assertEqual(
            errors,
            [{'email': 'This field cannot be repeated.'}, {'email': 'This field cannot be repeated.'}],
        )

    def test_multiple_unique_fields_accumulate_dict_keys(self):
        values = [
            {'email': 'a@x.com', 'phone': '111'},
            {'email': 'a@x.com', 'phone': '111'},
        ]

        with_error, errors = unique_fields(values, ['email', 'phone'], with_key=True)

        self.assertTrue(with_error)
        self.assertEqual(
            errors[0],
            {'email': 'This field cannot be repeated.', 'phone': 'This field cannot be repeated.'},
        )

    def test_empty_values(self):
        with_error, errors = unique_fields([], ['email'])

        self.assertFalse(with_error)
        self.assertEqual(errors, [])

    def test_empty_unique_fields_never_flags_error(self):
        values = [{'email': 'a@x.com'}, {'email': 'a@x.com'}]

        with_error, errors = unique_fields(values, [])

        self.assertFalse(with_error)
        self.assertEqual(errors, [[], []])

    def test_missing_key_raises_key_error(self):
        values = [{'email': 'a@x.com'}, {'phone': '111'}]

        with self.assertRaises(KeyError):
            unique_fields(values, ['email'])

    def test_unhashable_value_raises_type_error(self):
        values = [{'tags': ['a']}, {'tags': ['a']}]

        with self.assertRaises(TypeError):
            unique_fields(values, ['tags'])

    def test_custom_error_message(self):
        values = [{'email': 'a@x.com'}, {'email': 'a@x.com'}]

        _, errors = unique_fields(values, ['email'], error='ya existe')

        self.assertEqual(errors, [['ya existe'], ['ya existe']])


if __name__ == '__main__':
    unittest.main()

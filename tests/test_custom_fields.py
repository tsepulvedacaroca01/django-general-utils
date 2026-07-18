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

from django.db import models

from django_general_utils.models.fields import AdvancedCharField, FloatField


class AdvancedCharFieldConstructorTests(unittest.TestCase):
    def test_only_one_case_option_allowed(self):
        with self.assertRaises(AssertionError):
            AdvancedCharField(max_length=50, to_upper=True, to_lower=True)

    def test_no_case_option_is_fine(self):
        field = AdvancedCharField(max_length=50)

        self.assertFalse(field.to_upper)
        self.assertFalse(field.to_lower)
        self.assertFalse(field.to_title)

    def test_single_case_option_is_fine(self):
        field = AdvancedCharField(max_length=50, to_title=True)

        self.assertTrue(field.to_title)


class AdvancedCharFieldGetPrepValueTests(unittest.TestCase):
    def test_none_passthrough(self):
        field = AdvancedCharField(max_length=50, to_upper=True)

        self.assertIsNone(field.get_prep_value(None))

    def test_non_str_passthrough(self):
        field = AdvancedCharField(max_length=50, to_upper=True)

        self.assertEqual(field.get_prep_value(123), '123')

    def test_to_upper(self):
        field = AdvancedCharField(max_length=50, to_upper=True)

        self.assertEqual(field.get_prep_value('hello'), 'HELLO')

    def test_to_lower(self):
        field = AdvancedCharField(max_length=50, to_lower=True)

        self.assertEqual(field.get_prep_value('HELLO'), 'hello')

    def test_to_title(self):
        field = AdvancedCharField(max_length=50, to_title=True)

        self.assertEqual(field.get_prep_value('hello world'), 'Hello World')

    def test_left_strip(self):
        field = AdvancedCharField(max_length=50, left_strip=True)

        self.assertEqual(field.get_prep_value('  hello  '), 'hello  ')

    def test_right_strip(self):
        field = AdvancedCharField(max_length=50, right_strip=True)

        self.assertEqual(field.get_prep_value('  hello  '), '  hello')

    def test_strip(self):
        field = AdvancedCharField(max_length=50, strip=True)

        self.assertEqual(field.get_prep_value('  hello  '), 'hello')

    def test_combined_upper_and_strip(self):
        field = AdvancedCharField(max_length=50, to_upper=True, strip=True)

        self.assertEqual(field.get_prep_value('  hello  '), 'HELLO')

    def test_empty_string(self):
        field = AdvancedCharField(max_length=50, to_upper=True, strip=True)

        self.assertEqual(field.get_prep_value(''), '')


class FormattedNumberFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class _NumberModel(models.Model):
            amount = FloatField(null=True, blank=True)

            class Meta:
                app_label = 'tests'

        cls.NumberModel = _NumberModel

    def test_format_decimal_method_is_attached(self):
        instance = self.NumberModel(amount=1234.5)

        self.assertEqual(instance.get_amount_format_decimal(), '1.234,5')

    def test_format_currency_method_is_attached(self):
        instance = self.NumberModel(amount=1000)

        self.assertEqual(instance.get_amount_format_currency(), '$1.000')

    def test_none_value_returns_empty_string_for_decimal(self):
        instance = self.NumberModel(amount=None)

        self.assertEqual(instance.get_amount_format_decimal(), '')

    def test_none_value_returns_empty_string_for_currency(self):
        instance = self.NumberModel(amount=None)

        self.assertEqual(instance.get_amount_format_currency(), '')

    def test_currency_kwarg_override(self):
        instance = self.NumberModel(amount=1000)

        self.assertEqual(instance.get_amount_format_currency(currency='USD', locale='en_US'), '$1,000.00')


if __name__ == '__main__':
    unittest.main()

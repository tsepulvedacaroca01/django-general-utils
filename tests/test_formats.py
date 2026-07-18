import unittest
from decimal import Decimal

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

from django_general_utils.utils.formats import format_currency, format_decimal


class FormatCurrencyTests(unittest.TestCase):
    def test_default_clp_es_cl(self):
        self.assertEqual(format_currency(1000), '$1.000')

    def test_explicit_currency_and_locale(self):
        self.assertEqual(format_currency(1000, currency='USD', locale='en_US'), '$1,000.00')

    def test_decimal_value(self):
        self.assertEqual(format_currency(Decimal('1500.50'), currency='USD', locale='en_US'), '$1,500.50')

    def test_kwargs_passthrough(self):
        default = format_currency(1000, currency='USD', locale='en_US')
        custom = format_currency(1000, currency='USD', locale='en_US', format='#,##0.00 ¤¤¤')

        self.assertNotEqual(default, custom)

    def test_invalid_locale_raises(self):
        # Babel raises plain ValueError for a syntactically malformed
        # identifier (this one contains hyphens); UnknownLocaleError is
        # reserved for well-formed-but-unrecognized locale codes.
        with self.assertRaises(ValueError):
            format_currency(1000, locale='not-a-real-locale')


class FormatDecimalTests(unittest.TestCase):
    def test_default_locale(self):
        self.assertEqual(format_decimal(1234.5), '1.234,5')

    def test_explicit_locale(self):
        self.assertEqual(format_decimal(1234.5, locale='en_US'), '1,234.5')

    def test_integer_value(self):
        self.assertEqual(format_decimal(10), '10')

    def test_invalid_locale_raises(self):
        with self.assertRaises(ValueError):
            format_decimal(10, locale='not-a-real-locale')


if __name__ == '__main__':
    unittest.main()

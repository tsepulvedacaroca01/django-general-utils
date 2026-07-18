import unittest
import uuid

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

from django_general_utils.utils.is_valid_uuid import is_valid_uuid


class IsValidUuidTests(unittest.TestCase):
    def test_valid_uuid_string(self):
        self.assertTrue(is_valid_uuid('12345678-1234-5678-1234-567812345678'))

    def test_valid_uuid_uppercase(self):
        self.assertTrue(is_valid_uuid('12345678-1234-5678-1234-567812345678'.upper()))

    def test_valid_uuid_without_dashes(self):
        self.assertTrue(is_valid_uuid('12345678123456781234567812345678'))

    def test_actual_uuid_instance(self):
        self.assertTrue(is_valid_uuid(uuid.uuid4()))

    def test_empty_string(self):
        self.assertFalse(is_valid_uuid(''))

    def test_random_garbage(self):
        self.assertFalse(is_valid_uuid('not-a-uuid'))

    def test_none(self):
        self.assertFalse(is_valid_uuid(None))

    def test_int(self):
        self.assertFalse(is_valid_uuid(123))


if __name__ == '__main__':
    unittest.main()

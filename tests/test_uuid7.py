import time
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

from django_general_utils.utils.uuid7 import uuid7


class Uuid7Tests(unittest.TestCase):
    def test_returns_uuid_instance(self):
        self.assertIsInstance(uuid7(), uuid.UUID)

    def test_version_is_7(self):
        self.assertEqual(uuid7().version, 7)

    def test_variant_bits_are_rfc_4122(self):
        value = uuid7()
        self.assertEqual((value.int >> 62) & 0b11, 0b10)

    def test_timestamp_matches_current_time(self):
        before_ms = int(time.time() * 1000)
        value = uuid7()
        after_ms = int(time.time() * 1000)

        embedded_ms = value.int >> 80

        self.assertLessEqual(before_ms, embedded_ms)
        self.assertLessEqual(embedded_ms, after_ms)

    def test_successive_values_are_unique(self):
        values = {uuid7() for _ in range(1000)}
        self.assertEqual(len(values), 1000)

    def test_ordered_by_creation_time(self):
        first = uuid7()
        time.sleep(0.01)
        second = uuid7()

        self.assertLess(first.bytes, second.bytes)


if __name__ == '__main__':
    unittest.main()

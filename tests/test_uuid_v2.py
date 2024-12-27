import importlib.util
import os
import unittest
from unittest import mock

import django
from django.conf import settings


if not settings.configured:
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

from django.db import connection, models
from django.core.management import call_command


UUID_V2_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        '..',
        'django_general_utils',
        'models',
        'uuid_v2.py',
    )
)
UUID_V2_SPEC = importlib.util.spec_from_file_location('uuid_v2_under_test', UUID_V2_PATH)
UUID_V2_MODULE = importlib.util.module_from_spec(UUID_V2_SPEC)
UUID_V2_SPEC.loader.exec_module(UUID_V2_MODULE)
UUIDModelV2 = UUID_V2_MODULE.UUIDModelV2


class UUIDModelV2TestModel(UUIDModelV2):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_uuid_model_v2'


class UUIDModelV2SaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(UUIDModelV2TestModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(UUIDModelV2TestModel)
        super().tearDownClass()

    def setUp(self):
        UUIDModelV2TestModel.objects.all().delete()

    def test_assigns_incremental_id(self):
        first = UUIDModelV2TestModel.objects.create(name='first')
        second = UUIDModelV2TestModel.objects.create(name='second')

        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 2)

    def test_next_code_uses_numeric_id(self):
        UUIDModelV2TestModel.objects.create(name='first')

        self.assertEqual(UUIDModelV2TestModel.next_code(), '0000002')

    def test_retries_when_generated_id_collides(self):
        UUIDModelV2TestModel.objects.create(name='existing')
        instance = UUIDModelV2TestModel(name='retry')

        with mock.patch.object(UUIDModelV2TestModel, 'max_id', side_effect=[0, 1]):
            instance.save()

        self.assertEqual(instance.id, 2)
        self.assertEqual(UUIDModelV2TestModel.objects.count(), 2)


if __name__ == '__main__':
    unittest.main()


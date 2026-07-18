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

from django.core.management import call_command
from django.db import connection, models

from django_general_utils.models.base_without_safe_delete import BaseWithoutSafeDeleteModel


class BulkCreateDefaultIdModel(BaseWithoutSafeDeleteModel):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_bulk_create_default_id_model'


class BulkCreateCustomInitialIdModel(BaseWithoutSafeDeleteModel):
    _INITIAL_ID_ = 1000

    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_bulk_create_custom_initial_id_model'


class BulkCreateDynamicInitialIdModel(BaseWithoutSafeDeleteModel):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_bulk_create_dynamic_initial_id_model'

    @classmethod
    def get_initial_id(cls) -> int:
        return 500


class BulkCreateIdAssignmentTests(unittest.TestCase):
    _MODELS_ = (
        BulkCreateDefaultIdModel,
        BulkCreateCustomInitialIdModel,
        BulkCreateDynamicInitialIdModel,
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)

        with connection.schema_editor() as schema_editor:
            for _model in cls._MODELS_:
                schema_editor.create_model(_model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            for _model in cls._MODELS_:
                schema_editor.delete_model(_model)

        super().tearDownClass()

    def setUp(self):
        for _model in self._MODELS_:
            _model.objects.all().delete()

    def test_bulk_create_assigns_sequential_ids(self):
        instances = BulkCreateDefaultIdModel.objects.bulk_create([
            BulkCreateDefaultIdModel(name='first'),
            BulkCreateDefaultIdModel(name='second'),
            BulkCreateDefaultIdModel(name='third'),
        ])

        self.assertEqual([instance.id for instance in instances], [1, 2, 3])
        self.assertEqual(
            sorted(BulkCreateDefaultIdModel.objects.values_list('id', flat=True)),
            [1, 2, 3],
        )

    def test_bulk_create_continues_after_existing_rows(self):
        BulkCreateDefaultIdModel.objects.create(name='existing')

        instances = BulkCreateDefaultIdModel.objects.bulk_create([
            BulkCreateDefaultIdModel(name='second'),
            BulkCreateDefaultIdModel(name='third'),
        ])

        self.assertEqual([instance.id for instance in instances], [2, 3])

    def test_bulk_create_respects_preset_id(self):
        instances = BulkCreateDefaultIdModel.objects.bulk_create([
            BulkCreateDefaultIdModel(name='preset', id=50),
            BulkCreateDefaultIdModel(name='auto'),
        ])

        self.assertEqual(instances[0].id, 50)
        self.assertEqual(instances[1].id, 1)

    def test_bulk_create_starts_at_custom_initial_id(self):
        instances = BulkCreateCustomInitialIdModel.objects.bulk_create([
            BulkCreateCustomInitialIdModel(name='first'),
            BulkCreateCustomInitialIdModel(name='second'),
        ])

        self.assertEqual([instance.id for instance in instances], [1000, 1001])

    def test_bulk_create_starts_at_dynamically_resolved_initial_id(self):
        instances = BulkCreateDynamicInitialIdModel.objects.bulk_create([
            BulkCreateDynamicInitialIdModel(name='first'),
        ])

        self.assertEqual(instances[0].id, 500)

    def test_custom_initial_id_only_applies_when_table_is_empty(self):
        BulkCreateCustomInitialIdModel.objects.create(name='existing')

        instances = BulkCreateCustomInitialIdModel.objects.bulk_create([
            BulkCreateCustomInitialIdModel(name='second'),
        ])

        self.assertEqual(instances[0].id, 1001)


if __name__ == '__main__':
    unittest.main()

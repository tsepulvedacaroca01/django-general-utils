import unittest
from unittest import mock

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
from ordered_model.models import OrderedModel

from django_general_utils.models.managers.base_v2 import BaseV2Manager
from django_general_utils.models.uuid_v3 import UUIDModelV3


class UUIDModelV3TestBase(OrderedModel, UUIDModelV3):
    """
    Mirrors BaseV2's composition (OrderedModel + the manager that wires
    bulk_create -> _assign_auto_ids) but on top of UUIDModelV3 instead of
    UUIDModelV2, without pulling in the full ModelBaseV2Meta machinery
    (FieldTracker/signals), which is unrelated to what's under test here.
    """
    objects = BaseV2Manager()

    class Meta:
        abstract = True
        ordering = ('-uuid',)

    def save(self, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            self.full_clean()

        super().save(**kwargs)


class UUIDModelV3TestModel(UUIDModelV3TestBase):
    _ID_AS_CODE_PREFIX_ = 'VE-'
    _ID_AS_CODE_LENGTH_ = 5

    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_uuid_model_v3'


class UUIDModelV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(UUIDModelV3TestModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(UUIDModelV3TestModel)
        super().tearDownClass()

    def setUp(self):
        UUIDModelV3TestModel.objects.all().delete()

    def test_default_ordering_is_by_uuid(self):
        # UUIDModelV3's own default is `-uuid` (time-ordered PK, reuses its own index) — unlike
        # BaseV3, which deliberately overrides this back to `-created_at` (see
        # tests/test_base_v3.py::test_ordering_is_by_created_at) because BaseV3 is meant for
        # models migrating from BaseV2/uuid4 with legacy rows, where `-uuid` would sort those old
        # rows effectively at random. A model built directly on UUIDModelV3 (no legacy uuid4
        # data) doesn't have that problem, so it keeps the more efficient default.
        self.assertEqual(UUIDModelV3._meta.ordering, ('-uuid',))

    def test_uuid_pk_is_version_7(self):
        instance = UUIDModelV3TestModel.objects.create(name='first')

        self.assertEqual(instance.uuid.version, 7)

    def test_id_as_code_populated_on_create(self):
        instance = UUIDModelV3TestModel.objects.create(name='first')

        self.assertEqual(instance.id, 1)
        self.assertEqual(instance.id_as_code, 'VE-00001')

    def test_id_as_code_populated_with_preset_id(self):
        instance = UUIDModelV3TestModel.objects.create(name='preset', id=42)

        self.assertEqual(instance.id_as_code, 'VE-00042')

    def test_id_as_code_not_overwritten_if_already_set(self):
        instance = UUIDModelV3TestModel.objects.create(name='custom', id=42, id_as_code='CUSTOM-CODE')

        self.assertEqual(instance.id_as_code, 'CUSTOM-CODE')

    def test_id_as_code_populated_on_bulk_create(self):
        instances = UUIDModelV3TestModel.objects.bulk_create([
            UUIDModelV3TestModel(name='first'),
            UUIDModelV3TestModel(name='second'),
        ])

        self.assertEqual([instance.id_as_code for instance in instances], ['VE-00001', 'VE-00002'])

    def test_id_as_code_survives_retry_on_id_collision(self):
        UUIDModelV3TestModel.objects.create(name='existing')
        instance = UUIDModelV3TestModel(name='retry')

        with mock.patch.object(UUIDModelV3TestModel, 'max_id', side_effect=[0, 1]):
            instance.save()

        self.assertEqual(instance.id, 2)
        self.assertEqual(instance.id_as_code, 'VE-00002')

    def test_next_code_uses_current_prefix(self):
        UUIDModelV3TestModel.objects.create(name='first')

        self.assertEqual(UUIDModelV3TestModel.next_code(), 'VE-00002')


if __name__ == '__main__':
    unittest.main()

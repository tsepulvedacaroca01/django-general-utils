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

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, models

from django_general_utils.models import BaseV3
from django_general_utils.models.base_v3 import BaseV3 as BaseV3FromModule


class BaseV3TestModel(BaseV3):
    _ID_AS_CODE_PREFIX_ = 'BV3-'
    _ID_AS_CODE_LENGTH_ = 4

    name = models.CharField(max_length=64, null=True, blank=True)
    price = models.FloatField(null=True, blank=True)

    class Meta(BaseV3.Meta):
        # Subclassing BaseV3.Meta (instead of a bare `class Meta:`) is what makes Django carry
        # over `ordering` from the abstract base — a fresh Meta wouldn't inherit it.
        app_label = 'tests'
        db_table = 'test_base_v3_model'


class BaseV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(BaseV3TestModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(BaseV3TestModel)
        super().tearDownClass()

    def setUp(self):
        BaseV3TestModel.objects.all().delete()

    def test_exported_from_module_and_package_are_the_same_class(self):
        self.assertIs(BaseV3, BaseV3FromModule)

    def test_uuid_is_version_7(self):
        instance = BaseV3TestModel.objects.create(name='first')

        self.assertEqual(instance.uuid.version, 7)

    def test_id_as_code_populated_automatically(self):
        instance = BaseV3TestModel.objects.create(name='first')

        self.assertEqual(instance.id_as_code, 'BV3-0001')

    def test_bulk_create_populates_id_and_id_as_code(self):
        instances = BaseV3TestModel.objects.bulk_create([
            BaseV3TestModel(name='first'),
            BaseV3TestModel(name='second'),
        ])

        self.assertEqual([instance.id_as_code for instance in instances], ['BV3-0001', 'BV3-0002'])

    def test_full_clean_runs_on_save(self):
        with self.assertRaises(ValidationError):
            BaseV3TestModel.objects.create(name='x' * 100)

    def test_ordering_is_by_uuid(self):
        self.assertEqual(BaseV3TestModel._meta.ordering, ('-uuid',))

    def test_metaclass_adds_formatted_number_helpers(self):
        instance = BaseV3TestModel.objects.create(name='first', price=1234.5)

        self.assertTrue(hasattr(instance, 'get_price_format_decimal'))
        self.assertTrue(hasattr(instance, 'get_price_format_currency'))

    def test_field_tracker_is_present(self):
        instance = BaseV3TestModel.objects.create(name='first')

        self.assertTrue(hasattr(instance, 'tracker'))


if __name__ == '__main__':
    unittest.main()

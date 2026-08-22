import tempfile
import unittest
from pathlib import Path

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

from django_general_utils.management.commands.sync_id_as_code import (
    count_drift,
    discover_id_as_code_models,
    next_migration_number,
    render_migration,
    write_migration,
)
from django_general_utils.models.managers.base_v2 import BaseV2Manager
from django_general_utils.models.uuid_v3 import UUIDModelV3


class SyncIdAsCodeTestBase(OrderedModel, UUIDModelV3):
    objects = BaseV2Manager()

    class Meta:
        abstract = True
        ordering = ('-uuid',)

    def save(self, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            self.full_clean()

        super().save(**kwargs)


class SyncIdAsCodeModel(SyncIdAsCodeTestBase):
    _ID_AS_CODE_PREFIX_ = 'VE-'
    _ID_AS_CODE_LENGTH_ = 5

    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_sync_id_as_code_model'


class _FakeGraph:
    def __init__(self, leaves):
        self._leaves = leaves

    def leaf_nodes(self, app_label):
        return self._leaves


class _FakeLoader:
    def __init__(self, disk_migrations, leaves=()):
        self.disk_migrations = disk_migrations
        self.graph = _FakeGraph(leaves)


class SyncIdAsCodeCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(SyncIdAsCodeModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(SyncIdAsCodeModel)
        super().tearDownClass()

    def setUp(self):
        SyncIdAsCodeModel.objects.all().delete()
        self.addCleanup(setattr, SyncIdAsCodeModel, '_ID_AS_CODE_PREFIX_', 'VE-')

    def test_discover_id_as_code_models_finds_concrete_subclasses(self):
        self.assertIn(SyncIdAsCodeModel, discover_id_as_code_models())
        self.assertNotIn(UUIDModelV3, discover_id_as_code_models())

    def test_count_drift_is_zero_right_after_create(self):
        SyncIdAsCodeModel.objects.create(name='first')

        self.assertEqual(count_drift(SyncIdAsCodeModel), 0)

    def test_count_drift_detects_prefix_change(self):
        SyncIdAsCodeModel.objects.create(name='first')
        SyncIdAsCodeModel._ID_AS_CODE_PREFIX_ = 'NEW-'

        self.assertEqual(count_drift(SyncIdAsCodeModel), 1)

    def test_count_drift_detects_never_backfilled_rows(self):
        instance = SyncIdAsCodeModel.objects.create(name='first')
        SyncIdAsCodeModel.objects.filter(pk=instance.pk).update(id_as_code=None)

        self.assertEqual(count_drift(SyncIdAsCodeModel), 1)

    def test_next_migration_number_starts_at_one(self):
        loader = _FakeLoader(disk_migrations={})

        self.assertEqual(next_migration_number(loader, 'tests'), 1)

    def test_next_migration_number_continues_after_existing(self):
        loader = _FakeLoader(disk_migrations={
            ('tests', '0001_initial'): object(),
            ('tests', '0003_add_field'): object(),
            ('other_app', '0007_unrelated'): object(),
        })

        self.assertEqual(next_migration_number(loader, 'tests'), 4)

    def test_render_migration_bakes_in_prefix_suffix_length(self):
        content = render_migration(
            app_label='tests',
            models=[SyncIdAsCodeModel],
            dependencies=[('tests', '0001_initial')],
        )

        self.assertIn("Model = apps.get_model('tests', 'syncidascodemodel')", content)
        self.assertIn("Value('VE-')", content)
        self.assertIn('5 - Length', content)
        self.assertIn("migrations.RunPython(sync_id_as_code_syncidascodemodel, migrations.RunPython.noop)", content)
        self.assertIn("('tests', '0001_initial'),", content)

    def test_write_migration_creates_file_on_disk(self):
        loader = _FakeLoader(disk_migrations={}, leaves=[('tests', '0001_initial')])

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = write_migration('tests', [SyncIdAsCodeModel], loader, migrations_dir=tmp_dir)

            self.assertEqual(Path(file_path).name, '0001_sync_id_as_code.py')
            content = Path(file_path).read_text()
            self.assertIn('class Migration(migrations.Migration):', content)
            self.assertIn("('tests', '0001_initial'),", content)


if __name__ == '__main__':
    unittest.main()

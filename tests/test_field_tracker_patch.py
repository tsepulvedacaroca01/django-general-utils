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
from django_general_utils.models.constraints.check_flow_status import CheckFlowStatusConstraint

_STATUS_CHOICES = [('P', 'Pendiente'), ('E', 'En proceso'), ('C', 'Completado')]
_FLOW = {'P': ['E'], 'E': ['C'], 'C': []}


class FieldTrackerPatchModel(BaseV3):
    name = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=2, choices=_STATUS_CHOICES, default='P')

    class Meta(BaseV3.Meta):
        app_label = 'tests'
        db_table = 'test_field_tracker_patch_model'
        constraints = [
            CheckFlowStatusConstraint(
                name='field_tracker_patch_status_flow',
                flow=_FLOW,
                field='status',
                initial_statuses=['P'],
            ),
        ]


class FieldTrackerPatchTests(unittest.TestCase):
    """
    `_field_tracker_patch.py` fixes `model_utils.FieldTracker` for PKs generated in Python
    (`uuid7`, `BaseV2`/`BaseV3`). Without the patch, a freshly-constructed instance already has a
    truthy `pk` before ever being saved, so the tracker's `not instance.pk` heuristic wrongly
    treats it as "already has saved state" and captures whatever was passed to the constructor as
    the "saved"/previous value instead of leaving it empty. These tests exercise the real
    `model_utils` tracker (not a fake), since that's exactly what the patch touches.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(FieldTrackerPatchModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(FieldTrackerPatchModel)
        super().tearDownClass()

    def setUp(self):
        FieldTrackerPatchModel.objects.all().delete()

    def test_new_instance_pk_is_already_truthy(self):
        # Sanity check for the premise of the whole patch: with an AutoField PK, `pk` would be
        # None here. With uuid7, it's already set before the first save.
        instance = FieldTrackerPatchModel(name='a', status='P')

        self.assertIsNotNone(instance.pk)

    def test_new_instance_tracker_has_no_previous_value(self):
        instance = FieldTrackerPatchModel(name='a', status='P')

        self.assertIsNone(instance.tracker.previous('status'))

    def test_new_instance_reports_field_as_changed(self):
        # Regression: pre-patch, `set_saved_fields()` used `not instance.pk` to decide whether to
        # start with empty saved_data. Since uuid7 makes `pk` truthy immediately, it took the
        # `saved_data = self.current()` branch instead — capturing the constructor kwargs
        # (`status='P'`) as if they were the "previous" DB state. A field that's only ever set
        # once, at construction, and never touched again would then wrongly report
        # `has_changed() == False`.
        instance = FieldTrackerPatchModel(name='a', status='P')

        self.assertTrue(instance.tracker.has_changed('status'))

    def test_invalid_initial_status_rejected_even_when_only_set_via_constructor(self):
        # Regression, end to end through CheckFlowStatusConstraint: pre-patch, this used to save
        # successfully — has_changed('status') was False (bogus "saved" baseline == the
        # constructor value), so validate() returned early before ever reaching the
        # initial_statuses check.
        instance = FieldTrackerPatchModel(name='a', status='E')  # 'E' not in initial_statuses=['P']

        with self.assertRaises(ValidationError):
            instance.save()

    def test_valid_initial_status_saves_fine(self):
        instance = FieldTrackerPatchModel(name='a', status='P')
        instance.save()

        self.assertIsNotNone(instance.pk)

    def test_loaded_instance_tracker_resyncs_after_from_db(self):
        created = FieldTrackerPatchModel.objects.create(name='a', status='P')

        loaded = FieldTrackerPatchModel.objects.get(pk=created.pk)

        self.assertFalse(loaded.tracker.has_changed('status'))
        self.assertEqual(loaded.tracker.previous('status'), 'P')

    def test_loaded_instance_detects_real_status_change(self):
        created = FieldTrackerPatchModel.objects.create(name='a', status='P')

        loaded = FieldTrackerPatchModel.objects.get(pk=created.pk)
        loaded.status = 'E'

        self.assertTrue(loaded.tracker.has_changed('status'))
        self.assertEqual(loaded.tracker.previous('status'), 'P')

        loaded.save()  # P -> E is a valid transition, must not raise

    def test_invalid_transition_after_load_is_rejected(self):
        created = FieldTrackerPatchModel.objects.create(name='a', status='P')

        loaded = FieldTrackerPatchModel.objects.get(pk=created.pk)
        loaded.status = 'C'  # P -> C is not in the flow

        with self.assertRaises(ValidationError):
            loaded.save()


if __name__ == '__main__':
    unittest.main()

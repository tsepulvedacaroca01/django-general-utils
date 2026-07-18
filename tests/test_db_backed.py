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
from django.db import IntegrityError, connection, models
from django.db.models import Q
from rest_framework import serializers

from django_general_utils.models.base_without_safe_delete import BaseWithoutSafeDeleteModel
from django_general_utils.models.constraints.check_max_rows_without_safe_delete_contraint import (
    CheckRowsModelWithoutSafeDeleteConstraint,
)
from django_general_utils.models.constraints.unique_constraint import UniqueConstraint
from django_general_utils.models.constraints.unique_without_safe_delete_constraint import (
    UniqueWithoutSafeDeleteConstraint,
)
from django_general_utils.utils.drf.fields.nested_primary_key_related_field import PrimaryKeyRelatedField
from django_general_utils.utils.drf.validations.unique_together import validate_unique_together
from django_general_utils.utils.factory.django.django_model_factory import DjangoModelFactory


class UniqueConstraintDefinitionTests(unittest.TestCase):
    """`UniqueConstraint` (safedelete-aware): construction/naming only.

    Enforcing it end-to-end needs a `BaseModel` (safedelete) subclass, which
    pulls in HistoricalRecords' shadow table + FieldTracker; not covered
    here to keep the fixture light. `UniqueWithoutSafeDeleteConstraint`
    below *is* exercised end-to-end since it has no safedelete dependency.
    """

    def test_default_condition_excludes_soft_deleted(self):
        from safedelete.config import FIELD_NAME

        constraint = UniqueConstraint(prefix='p', fields=['code'])

        self.assertEqual(constraint.condition, models.Q(**{f'{FIELD_NAME}__isnull': True}))

    def test_include_deleted_true_has_no_condition(self):
        constraint = UniqueConstraint(prefix='p', fields=['code'], include_deleted=True)

        self.assertIsNone(constraint.condition)

    def test_auto_generated_name_default(self):
        constraint = UniqueConstraint(prefix='mymodel', fields=['email'])

        self.assertEqual(constraint.name, 'mymodel_unique_active_email')

    def test_auto_generated_name_include_deleted(self):
        constraint = UniqueConstraint(prefix='mymodel', fields=['email'], include_deleted=True)

        self.assertEqual(constraint.name, 'mymodel_unique_email')

    def test_explicit_name_is_respected(self):
        constraint = UniqueConstraint(prefix='mymodel', fields=['email'], name='custom_name')

        self.assertEqual(constraint.name, 'custom_name')


class _UniqueConstraintModel(BaseWithoutSafeDeleteModel):
    code = models.CharField(max_length=20)

    class Meta:
        app_label = 'tests'
        db_table = 'test_unique_without_sd_model'
        constraints = [
            UniqueWithoutSafeDeleteConstraint(prefix='uniqcm', fields=['code']),
        ]


class _MaxRowsModel(BaseWithoutSafeDeleteModel):
    name = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_max_rows_model'
        constraints = [
            # check=Q() (not the check=None default - see
            # test_default_check_none_raises_type_error below for why).
            CheckRowsModelWithoutSafeDeleteConstraint(max_rows=2, name='max_2_rows', check=Q()),
        ]


class _RelatedModel(models.Model):
    name = models.CharField(max_length=20)

    class Meta:
        app_label = 'tests'
        db_table = 'test_related_model_for_pk_field'


class _PersonUniqueTogetherModel(models.Model):
    email = models.CharField(max_length=100)

    class Meta:
        app_label = 'tests'
        db_table = 'test_person_unique_together_model'


class _UniqueDbModel(models.Model):
    code = models.CharField(max_length=20, unique=True)
    other_code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_unique_db_model_for_factory'


class _UniqueDbModelFactory(DjangoModelFactory):
    class Meta:
        model = _UniqueDbModel
        django_get_or_create = ('code',)

    code = 'ABC'
    other_code = None


_ALL_MODELS = (
    _UniqueConstraintModel,
    _MaxRowsModel,
    _RelatedModel,
    _PersonUniqueTogetherModel,
    _UniqueDbModel,
)


class _DbBackedTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)

        with connection.schema_editor() as schema_editor:
            for model in _ALL_MODELS:
                schema_editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            for model in _ALL_MODELS:
                schema_editor.delete_model(model)

        super().tearDownClass()

    def setUp(self):
        for model in _ALL_MODELS:
            model.objects.all().delete()


class UniqueWithoutSafeDeleteConstraintDbTests(_DbBackedTestCase):
    def test_auto_generated_name(self):
        constraint = _UniqueConstraintModel._meta.constraints[0]

        self.assertEqual(constraint.name, 'uniqcm_unique_active_code')

    def test_duplicate_raises_validation_error(self):
        _UniqueConstraintModel.objects.create(code='DUP')

        with self.assertRaises(ValidationError):
            _UniqueConstraintModel.objects.create(code='DUP')

    def test_different_value_is_allowed(self):
        _UniqueConstraintModel.objects.create(code='A')
        _UniqueConstraintModel.objects.create(code='B')

        self.assertEqual(_UniqueConstraintModel.objects.count(), 2)


class CheckRowsModelWithoutSafeDeleteConstraintDbTests(_DbBackedTestCase):
    def test_default_check_none_raises_type_error(self):
        # Known bug: with the default check=None, `Q(self.check)` wraps a
        # bare `None` as a child node. Resolving that Q via `.check(...)`
        # crashes with TypeError (not FieldError, so it's not swallowed by
        # the surrounding except) instead of being treated as "no filter".
        # This means the constraint is unusable with its own default.
        constraint = CheckRowsModelWithoutSafeDeleteConstraint(max_rows=1, name='no_check')
        instance = _MaxRowsModel.objects.create(name='a')

        with self.assertRaises(TypeError):
            constraint.validate(model=_MaxRowsModel, instance=instance)

    def test_allows_up_to_max_rows(self):
        _MaxRowsModel.objects.create(name='a')
        _MaxRowsModel.objects.create(name='b')

        self.assertEqual(_MaxRowsModel.objects.count(), 2)

    def test_raises_when_exceeding_max_rows(self):
        _MaxRowsModel.objects.create(name='a')
        _MaxRowsModel.objects.create(name='b')

        with self.assertRaises(ValidationError):
            _MaxRowsModel.objects.create(name='c')

    def test_updating_existing_row_does_not_count_itself(self):
        first = _MaxRowsModel.objects.create(name='a')
        _MaxRowsModel.objects.create(name='b')

        first.name = 'updated'
        first.save()

        first.refresh_from_db()
        self.assertEqual(first.name, 'updated')


class PrimaryKeyRelatedFieldDbTests(_DbBackedTestCase):
    def test_resolves_instance_from_pk(self):
        obj = _RelatedModel.objects.create(name='x')
        field = PrimaryKeyRelatedField(queryset=_RelatedModel.objects.all())

        self.assertEqual(field.to_internal_value(obj.pk), obj)

    def test_boolean_value_is_rejected_even_if_it_matches_a_pk(self):
        _RelatedModel.objects.create(name='x')  # gets pk=1, same value as `True`
        field = PrimaryKeyRelatedField(queryset=_RelatedModel.objects.all())

        with self.assertRaises(serializers.ValidationError):
            field.to_internal_value(True)

    def test_missing_pk_raises_does_not_exist(self):
        field = PrimaryKeyRelatedField(queryset=_RelatedModel.objects.all())

        with self.assertRaises(serializers.ValidationError):
            field.to_internal_value(99999)

    def test_only_pk_true_returns_raw_pk_not_instance(self):
        obj = _RelatedModel.objects.create(name='x')
        field = PrimaryKeyRelatedField(queryset=_RelatedModel.objects.all(), only_pk=True)

        self.assertEqual(field.to_internal_value(obj.pk), obj.pk)
        self.assertNotIsInstance(field.to_internal_value(obj.pk), _RelatedModel)


class ValidateUniqueTogetherDbTests(_DbBackedTestCase):
    def test_no_matching_row_returns_false(self):
        result = validate_unique_together(None, _PersonUniqueTogetherModel, {'email': 'a@x.com'})

        self.assertFalse(result)

    def test_matching_row_with_no_instance_returns_true(self):
        _PersonUniqueTogetherModel.objects.create(email='a@x.com')

        result = validate_unique_together(None, _PersonUniqueTogetherModel, {'email': 'a@x.com'})

        self.assertTrue(result)

    def test_matching_row_excludes_current_instance(self):
        person = _PersonUniqueTogetherModel.objects.create(email='a@x.com')

        result = validate_unique_together(person, _PersonUniqueTogetherModel, {'email': 'a@x.com'})

        self.assertFalse(result)

    def test_matching_row_belonging_to_a_different_instance_returns_true(self):
        _PersonUniqueTogetherModel.objects.create(email='a@x.com')
        other_person = _PersonUniqueTogetherModel.objects.create(email='b@x.com')

        result = validate_unique_together(other_person, _PersonUniqueTogetherModel, {'email': 'a@x.com'})

        self.assertTrue(result)


class DjangoModelFactoryGetOrCreateTests(_DbBackedTestCase):
    def test_second_call_with_same_unique_field_returns_existing_instance(self):
        first = _UniqueDbModelFactory(code='ABC')
        second = _UniqueDbModelFactory(code='ABC')

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(_UniqueDbModel.objects.count(), 1)

    def test_different_unique_field_creates_a_new_instance(self):
        first = _UniqueDbModelFactory(code='AAA')
        second = _UniqueDbModelFactory(code='BBB')

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(_UniqueDbModel.objects.count(), 2)

    def test_integrity_error_on_a_field_outside_django_get_or_create_propagates(self):
        # `other_code` collides but is NOT part of django_get_or_create
        # (only `code` is), so the get() fallback looks up the wrong field
        # and the original IntegrityError propagates instead of being
        # swallowed.
        _UniqueDbModelFactory(code='X1', other_code='SAME')

        with self.assertRaises(IntegrityError):
            _UniqueDbModelFactory(code='X2', other_code='SAME')


if __name__ == '__main__':
    unittest.main()

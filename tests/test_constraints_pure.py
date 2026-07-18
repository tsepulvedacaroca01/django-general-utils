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
from django.db import models
from safedelete.config import FIELD_NAME

from django_general_utils.models.constraints.base_constraint import BaseConstraint
from django_general_utils.models.constraints.check_editable_constraint import CheckEditableConstraint
from django_general_utils.models.constraints.check_flow_status import CheckFlowStatusConstraint
from django_general_utils.models.constraints.check_model_relation_constraint import CheckModelRelationConstraint


class _State:
    def __init__(self, adding):
        self.adding = adding


class _FakeInstance:
    """Bare stand-in for a model instance - has just enough shape for
    constraint.validate() to run without touching a real model/DB."""

    def __init__(self, adding=True, deleted=None, **extra):
        self._state = _State(adding)
        setattr(self, FIELD_NAME, deleted)

        for key, value in extra.items():
            setattr(self, key, value)


class BaseConstraintTests(unittest.TestCase):
    def test_dict_violation_error_message_returned_as_is(self):
        constraint = BaseConstraint(name='c', violation_error_message={'field': 'bad value'})

        self.assertEqual(constraint.get_violation_error_message(), {'field': 'bad value'})

    def test_string_violation_error_message_delegates_to_super(self):
        constraint = BaseConstraint(name='c', violation_error_message='custom message')

        self.assertEqual(constraint.get_violation_error_message(), 'custom message')


class CheckModelRelationConstraintTests(unittest.TestCase):
    """Truth table for `check(instance)`'s return value.

    Known bug: `check` returning True *or* None both raise ValidationError.
    Only False (or another falsy-but-not-None value) passes - this is the
    opposite of the common "True == valid" convention.
    """

    def test_check_none_is_required(self):
        constraint = CheckModelRelationConstraint(name='c', check=None)

        with self.assertRaises(AssertionError):
            constraint.validate(model=None, instance=_FakeInstance())

    def test_check_returning_false_passes(self):
        constraint = CheckModelRelationConstraint(name='c', check=lambda instance: False)

        self.assertIsNone(constraint.validate(model=None, instance=_FakeInstance()))

    def test_check_returning_true_raises(self):
        constraint = CheckModelRelationConstraint(name='c', check=lambda instance: True)

        with self.assertRaises(ValidationError):
            constraint.validate(model=None, instance=_FakeInstance())

    def test_check_returning_none_raises(self):
        def _no_return(instance):
            return None

        constraint = CheckModelRelationConstraint(name='c', check=_no_return)

        with self.assertRaises(ValidationError):
            constraint.validate(model=None, instance=_FakeInstance())

    def test_check_returning_string_raises_with_that_message(self):
        constraint = CheckModelRelationConstraint(name='c', check=lambda instance: 'custom error')

        with self.assertRaises(ValidationError) as ctx:
            constraint.validate(model=None, instance=_FakeInstance())

        self.assertIn('custom error', ctx.exception.messages)

    def test_check_returning_dict_raises_with_that_dict(self):
        constraint = CheckModelRelationConstraint(name='c', check=lambda instance: {'field': ['bad']})

        with self.assertRaises(ValidationError) as ctx:
            constraint.validate(model=None, instance=_FakeInstance())

        self.assertEqual(ctx.exception.message_dict, {'field': ['bad']})

    def test_skips_validation_on_create_when_validate_on_create_false(self):
        constraint = CheckModelRelationConstraint(
            name='c', check=lambda instance: True, validate_on_create=False,
        )

        self.assertIsNone(constraint.validate(model=None, instance=_FakeInstance(adding=True)))

    def test_skips_validation_on_update_when_validate_on_update_false(self):
        constraint = CheckModelRelationConstraint(
            name='c', check=lambda instance: True, validate_on_update=False,
        )

        self.assertIsNone(constraint.validate(model=None, instance=_FakeInstance(adding=False)))

    def test_validate_on_delete_true_skips_validation_for_deleted_instance(self):
        # validate_on_delete=True actually means "this constraint no longer
        # applies once the instance is soft-deleted" - not "validate on
        # delete" as the name suggests.
        constraint = CheckModelRelationConstraint(
            name='c', check=lambda instance: True, validate_on_delete=True,
        )
        deleted_instance = _FakeInstance(deleted='2024-01-01T00:00:00')

        self.assertIsNone(constraint.validate(model=None, instance=deleted_instance))

    def test_validate_on_delete_false_still_validates_deleted_instance(self):
        constraint = CheckModelRelationConstraint(
            name='c', check=lambda instance: True, validate_on_delete=False,
        )
        deleted_instance = _FakeInstance(deleted='2024-01-01T00:00:00')

        with self.assertRaises(ValidationError):
            constraint.validate(model=None, instance=deleted_instance)


class CheckEditableConstraintTests(unittest.TestCase):
    class _FakeTracker:
        def __init__(self, changed_fields):
            self._changed_fields = set(changed_fields)

        def has_changed(self, field):
            return field in self._changed_fields

    def test_requires_at_least_one_field(self):
        # The `len(self.fields) > 0` assertion lives inside validate(), not
        # __init__ - constructing with fields=[] alone does not raise.
        constraint = CheckEditableConstraint(name='c', fields=[])
        instance = _FakeInstance(adding=False, tracker=self._FakeTracker([]))

        with self.assertRaises(AssertionError):
            constraint.validate(model=None, instance=instance)

    def test_requires_tracker_attribute(self):
        constraint = CheckEditableConstraint(name='c', fields=['status'])
        instance = _FakeInstance(adding=False)

        with self.assertRaises(AssertionError):
            constraint.validate(model=None, instance=instance)

    def test_skips_validation_when_creating(self):
        constraint = CheckEditableConstraint(name='c', fields=['status'])
        instance = _FakeInstance(adding=True, tracker=self._FakeTracker(['status']))

        self.assertIsNone(constraint.validate(model=None, instance=instance))

    def test_raises_when_editable_field_changed_on_update(self):
        constraint = CheckEditableConstraint(name='c', fields=['status'])
        instance = _FakeInstance(adding=False, tracker=self._FakeTracker(['status']))

        with self.assertRaises(ValidationError) as ctx:
            constraint.validate(model=None, instance=instance)

        self.assertIn('status', ctx.exception.message_dict)

    def test_passes_when_field_unchanged_on_update(self):
        constraint = CheckEditableConstraint(name='c', fields=['status'])
        instance = _FakeInstance(adding=False, tracker=self._FakeTracker([]))

        self.assertIsNone(constraint.validate(model=None, instance=instance))

    def test_eq_raises_name_error(self):
        # Known bug, worse than a mere wrong-class check: __eq__ references
        # `CheckModelRelationConstraint`, which this module never imports.
        # Comparing any two CheckEditableConstraint instances with `==`
        # crashes with NameError instead of comparing them.
        first = CheckEditableConstraint(name='c', fields=['a'])
        second = CheckEditableConstraint(name='c', fields=['b'])

        with self.assertRaises(NameError):
            first.__eq__(second)


class CheckFlowStatusConstraintTests(unittest.TestCase):
    FLOW = {'P': ['E', 'C'], 'E': ['F', 'C'], 'F': ['C'], 'C': [], 'CE': []}

    class _FakeTracker:
        def __init__(self, previous_value, changed=True):
            self._previous_value = previous_value
            self._changed = changed

        def has_changed(self, field):
            return self._changed

        def previous(self, field):
            return self._previous_value

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class _FlowModel(models.Model):
            status = models.CharField(
                max_length=2,
                choices=[('P', 'Pendiente'), ('E', 'Enviado'), ('F', 'Facturado'), ('C', 'Cancelado')],
            )

            class Meta:
                app_label = 'tests'

        cls.FlowModel = _FlowModel

    def _instance(self, current_status, previous_status, adding=False, changed=True):
        return _FakeInstance(
            adding=adding,
            status=current_status,
            tracker=self._FakeTracker(previous_status, changed=changed),
        )

    def test_requires_tracker_attribute(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = _FakeInstance(status='P')

        with self.assertRaises(AssertionError):
            constraint.validate(model=self.FlowModel, instance=instance)

    def test_field_not_changed_skips_validation(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = self._instance('F', 'P', adding=False, changed=False)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))

    def test_valid_initial_status_on_create(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW, initial_statuses=['P'])
        instance = self._instance('P', None, adding=True)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))

    def test_invalid_initial_status_on_create_raises(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW, initial_statuses=['P'])
        instance = self._instance('F', None, adding=True)

        with self.assertRaises(ValidationError) as ctx:
            constraint.validate(model=self.FlowModel, instance=instance)

        self.assertIn('status', ctx.exception.message_dict)

    def test_last_value_none_on_update_skips_transition_check(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = self._instance('F', None, adding=False)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))

    def test_no_op_transition_passes(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = self._instance('P', 'P', adding=False)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))

    def test_allowed_transition_passes(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = self._instance('E', 'P', adding=False)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))

    def test_disallowed_transition_raises_with_expected_message(self):
        constraint = CheckFlowStatusConstraint(name='c', flow=self.FLOW)
        instance = self._instance('F', 'P', adding=False)

        with self.assertRaises(ValidationError) as ctx:
            constraint.validate(model=self.FlowModel, instance=instance)

        self.assertEqual(
            ctx.exception.message_dict['status'],
            ['No puedes avanzar este estado a "F" debido a que su valor actual "P" no lo permite.'],
        )

    def test_skip_validate_callable_bypasses_transition_check(self):
        constraint = CheckFlowStatusConstraint(
            name='c', flow=self.FLOW, skip_validate=lambda instance, last, current: True,
        )
        instance = self._instance('F', 'P', adding=False)

        self.assertIsNone(constraint.validate(model=self.FlowModel, instance=instance))


if __name__ == '__main__':
    unittest.main()

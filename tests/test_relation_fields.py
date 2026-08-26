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

from django.db import models
from django.db.models.lookups import IsNull

from django_general_utils.models import BaseModel, BaseV3
from django_general_utils.models.fields import ForeignKey, OneToOneField


class _ExtraRestrictionBaseModelTarget(BaseModel):
    # app_label='auth' (not 'tests'): django-simple-history's HistoricalRecords (auto-attached by
    # BaseModel's metaclass) needs a real, registered AppConfig for the model's app_label —
    # the 'tests' app_label used everywhere else in this repo isn't a real installed app, only
    # UUIDModelV2/V3-based mixins (no HistoricalRecords) get away with that.
    class Meta:
        app_label = 'auth'
        db_table = 'test_extra_restriction_basemodel_target'


class _ExtraRestrictionBaseV3Target(BaseV3):
    class Meta(BaseV3.Meta):
        app_label = 'tests'
        db_table = 'test_extra_restriction_basev3_target'


class _ExtraRestrictionBaseModelToBaseModel(BaseModel):
    fk_target = ForeignKey(_ExtraRestrictionBaseModelTarget, on_delete=models.CASCADE, null=True, blank=True)
    o2o_target = OneToOneField(
        _ExtraRestrictionBaseModelTarget, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
    )

    class Meta:
        app_label = 'auth'
        db_table = 'test_extra_restriction_bm_to_bm'


class _ExtraRestrictionBaseModelToBaseV3(BaseModel):
    fk_target = ForeignKey(_ExtraRestrictionBaseV3Target, on_delete=models.CASCADE, null=True, blank=True)
    o2o_target = OneToOneField(
        _ExtraRestrictionBaseV3Target, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
    )

    class Meta:
        app_label = 'auth'
        db_table = 'test_extra_restriction_bm_to_v3'


class _ExtraRestrictionBaseV3ToBaseModel(BaseV3):
    fk_target = ForeignKey(_ExtraRestrictionBaseModelTarget, on_delete=models.CASCADE, null=True, blank=True)
    o2o_target = OneToOneField(
        _ExtraRestrictionBaseModelTarget, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
    )

    class Meta(BaseV3.Meta):
        app_label = 'tests'
        db_table = 'test_extra_restriction_v3_to_bm'


class _ExtraRestrictionBaseV3ToBaseV3(BaseV3):
    fk_target = ForeignKey(_ExtraRestrictionBaseV3Target, on_delete=models.CASCADE, null=True, blank=True)
    o2o_target = OneToOneField(
        _ExtraRestrictionBaseV3Target, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
    )

    class Meta(BaseV3.Meta):
        app_label = 'tests'
        db_table = 'test_extra_restriction_v3_to_v3'


class GetExtraRestrictionTests(unittest.TestCase):
    """
    `get_extra_restriction` adds a `deleted_at IS NULL` SQL restriction so joins skip
    soft-deleted rows. That only makes sense when both sides of the relation are `BaseModel`
    (safedelete) — `BaseV2`/`BaseV3` models have no `deleted_at` column at all, so applying the
    restriction there would reference a column that doesn't exist. Doesn't need any DB table:
    `get_extra_restriction` only builds a SQL expression from the field's static model/remote
    model, it never executes a query.
    """

    def test_none_when_both_sides_are_basemodel_is_the_only_case_that_restricts(self):
        field = _ExtraRestrictionBaseModelToBaseModel._meta.get_field('fk_target')
        restriction = field.get_extra_restriction('t1', 't2')

        self.assertIsInstance(restriction, IsNull)

    def test_one_to_one_none_when_both_sides_are_basemodel_is_the_only_case_that_restricts(self):
        field = _ExtraRestrictionBaseModelToBaseModel._meta.get_field('o2o_target')
        restriction = field.get_extra_restriction('t1', 't2')

        self.assertIsInstance(restriction, IsNull)

    def test_foreign_key_no_restriction_when_target_is_not_basemodel(self):
        field = _ExtraRestrictionBaseModelToBaseV3._meta.get_field('fk_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))

    def test_foreign_key_no_restriction_when_source_is_not_basemodel(self):
        field = _ExtraRestrictionBaseV3ToBaseModel._meta.get_field('fk_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))

    def test_foreign_key_no_restriction_when_neither_side_is_basemodel(self):
        field = _ExtraRestrictionBaseV3ToBaseV3._meta.get_field('fk_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))

    def test_one_to_one_no_restriction_when_target_is_not_basemodel(self):
        field = _ExtraRestrictionBaseModelToBaseV3._meta.get_field('o2o_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))

    def test_one_to_one_no_restriction_when_source_is_not_basemodel(self):
        field = _ExtraRestrictionBaseV3ToBaseModel._meta.get_field('o2o_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))

    def test_one_to_one_no_restriction_when_neither_side_is_basemodel(self):
        field = _ExtraRestrictionBaseV3ToBaseV3._meta.get_field('o2o_target')

        self.assertIsNone(field.get_extra_restriction('t1', 't2'))


if __name__ == '__main__':
    unittest.main()

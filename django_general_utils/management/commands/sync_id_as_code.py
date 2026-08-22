import os

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.loader import MigrationLoader

from ...models.uuid_v3 import UUIDModelV3

MIGRATION_TEMPLATE = '''from django.db import migrations, models
from django.db.models import Value
from django.db.models.functions import Concat, Length, Cast, Repeat


{forward_functions}

class Migration(migrations.Migration):

    dependencies = [
{dependencies}
    ]

    operations = [
{operations}
    ]
'''

FORWARD_FUNCTION_TEMPLATE = '''def {function_name}(apps, schema_editor):
    Model = apps.get_model({app_label!r}, {model_name!r})
    Model.objects.filter(id__isnull=False).update(
        id_as_code=Concat(
            Value({prefix!r}),
            Repeat(Value('0'), {length!r} - Length(Cast('id', output_field=models.CharField()))),
            Cast('id', output_field=models.CharField()),
            Value({suffix!r}),
            output_field=models.CharField(),
        )
    )
'''


def discover_id_as_code_models() -> list:
    """
    Concrete (non-abstract) models that subclass ``UUIDModelV3``, i.e. models
    with a real ``id_as_code`` column that needs to stay in sync with
    ``_ID_AS_CODE_PREFIX_``/``_ID_AS_CODE_SUFFIX_``/``_ID_AS_CODE_LENGTH_``.
    """
    # ``apps.get_models()`` only returns models belonging to a registered
    # ``AppConfig``. ``apps.all_models`` also covers models whose ``Meta.app_label``
    # doesn't correspond to an installed app (a pattern this project's own
    # test suite relies on), so it's the more robust source to scan here.
    return [
        model
        for app_models in apps.all_models.values()
        for model in app_models.values()
        if issubclass(model, UUIDModelV3) and not model._meta.abstract
    ]


def count_drift(model, using=None) -> int:
    """
    Count rows whose stored ``id_as_code`` no longer matches what the
    model's current prefix/suffix/length would produce.
    """
    return model._id_queryset(using=using).filter(
        id__isnull=False
    ).exclude(
        id_as_code=model._id_as_code_expression()
    ).count()


def next_migration_number(loader: MigrationLoader, app_label: str) -> int:
    existing_numbers = [
        int(name[:4])
        for (label, name) in loader.disk_migrations
        if label == app_label and name[:4].isdigit()
    ]

    return (max(existing_numbers) + 1) if existing_numbers else 1


def render_migration(app_label: str, models: list, dependencies: list) -> str:
    forward_functions = []
    operations = []

    for model in models:
        model_name = model._meta.model_name
        function_name = f'sync_id_as_code_{model_name}'

        forward_functions.append(
            FORWARD_FUNCTION_TEMPLATE.format(
                function_name=function_name,
                app_label=app_label,
                model_name=model_name,
                prefix=model._ID_AS_CODE_PREFIX_,
                suffix=model._ID_AS_CODE_SUFFIX_,
                length=model._ID_AS_CODE_LENGTH_,
            )
        )
        operations.append(f'        migrations.RunPython({function_name}, migrations.RunPython.noop),')

    dependencies_lines = '\n'.join(
        f'        {dependency!r},' for dependency in dependencies
    ) or '        # no prior migrations for this app'

    return MIGRATION_TEMPLATE.format(
        forward_functions='\n\n'.join(forward_functions),
        dependencies=dependencies_lines,
        operations='\n'.join(operations),
    )


def write_migration(app_label: str, models: list, loader: MigrationLoader, migrations_dir: str = None) -> str:
    """
    Render and write a data migration that backfills ``id_as_code`` for
    ``models`` (all belonging to ``app_label``) using their current
    prefix/suffix/length. ``migrations_dir`` is overridable for tests; it
    defaults to the app's real ``migrations`` package.
    """
    if migrations_dir is None:
        migrations_dir = os.path.join(apps.get_app_config(app_label).path, 'migrations')

    os.makedirs(migrations_dir, exist_ok=True)

    file_name = f'{next_migration_number(loader, app_label):04d}_sync_id_as_code.py'
    file_path = os.path.join(migrations_dir, file_name)
    dependencies = loader.graph.leaf_nodes(app_label)

    with open(file_path, 'w') as migration_file:
        migration_file.write(render_migration(app_label, models, dependencies))

    return file_path


class Command(BaseCommand):
    help = (
        'Detect id_as_code drift on UUIDModelV3 subclasses (stale prefix/suffix/length '
        'or never-backfilled rows) and generate a data migration per affected app to fix it.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Only report drifted models (exit with an error if any); do not write migration files.',
        )

    def handle(self, *args, **options):
        drifted_by_app = {}

        for model in discover_id_as_code_models():
            drifted_count = count_drift(model)

            if drifted_count == 0:
                continue

            drifted_by_app.setdefault(model._meta.app_label, []).append(model)
            self.stdout.write(f'{model._meta.label} has {drifted_count} row(s) with a stale id_as_code.')

        if not drifted_by_app:
            self.stdout.write(self.style.SUCCESS('id_as_code is already in sync for every model.'))
            return

        if options['check']:
            raise CommandError('id_as_code drift detected (see above). Run without --check to generate migrations.')

        loader = MigrationLoader(connections[DEFAULT_DB_ALIAS], ignore_no_migrations=True)

        for app_label, models in drifted_by_app.items():
            file_path = write_migration(app_label, models, loader)
            self.stdout.write(self.style.SUCCESS(f'Wrote {file_path}'))

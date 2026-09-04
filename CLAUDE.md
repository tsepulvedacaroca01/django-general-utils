# CLAUDE.md

Guía para trabajar en este repo con Claude Code. Ver también `docs/00-contexto-libreria.md` (contexto
completo), `docs/01-tests.md` (convenciones de tests) y `docs/02-python-style.md` (estilo/ruff) — este
archivo es un resumen orientado a acción, no reemplaza esos docs.

## Qué es este repo

`django-general-utils` es una **librería** Django reutilizable (mixins abstractos, managers/querysets,
campos/constraints custom, utils de DRF, factories de test) — no un proyecto con modelos de negocio
propios. Se gestiona con **uv** (`pyproject.toml` + `uv.lock`). Requiere Postgres en producción; los tests
corren sobre sqlite, así que todo lo Postgres-only (`ArrayField`, funciones `array_*`/`clean_html`/
`formatted_datetime`, `postgres/search*.py`, `RandomNumber` en Postgres) no tiene cobertura de test real
en este repo — solo se puede validar su lógica de construcción de queryset/branching, no su ejecución SQL.

## Cómo correr algo

Nunca hay entorno Python utilizable en el host — todo corre en Docker:

```bash
docker-compose -f docker-compose.dev.yml build
docker-compose -f docker-compose.dev.yml up --abort-on-container-exit          # toda la suite
docker-compose -f docker-compose.dev.yml run --rm app-django-django-general-utils-dev \
    bash -c "uv run pytest tests/test_X.py -v -p no:xdist"                     # un archivo
docker-compose -f docker-compose.dev.yml run --rm app-django-django-general-utils-dev \
    bash -c "uv run ruff check ."                                              # lint
```

Tras tocar `pyproject.toml` (`dependencies`/`dependency-groups`), correr `uv lock` en el host (uv está
instalado ahí) y commitear el `uv.lock` actualizado — el `Dockerfile` usa `uv sync --frozen`, así que un
lock desactualizado hace fallar el build.

Cualquier `docker-compose run ... uv run ...` puede reescribir `uv.lock` solo (markers de resolución
específicos de la plataforma del contenedor), sin que haya un cambio de dependencias real de por medio.
Revisar `git status`/`git diff uv.lock` después de correr comandos y hacer `git restore uv.lock` si el
único cambio es ese ruido — no commitearlo.

Si la red del host/Docker está caída, `docker-compose run` falla igual (reinstala el paquete local en cada
invocación por el bind mount, y eso intenta resolver contra PyPI). Agregar `--no-sync` (`uv run --no-sync
pytest ...`) corre directo contra lo que ya está en `/opt/venv`, sin red — sirve mientras no se haya
tocado `pyproject.toml`/`uv.lock`.

## Patrón de tests (importante, no es el patrón "normal" de Django)

- `pytest.ini` tiene `python_files = tests/*.py` — los archivos de test deben vivir **directo** bajo
  `tests/`, no en subcarpetas.
- No hay `pytest-django`. Cada archivo de test configura Django a mano al importarse
  (`if not settings.configured: settings.configure(...); django.setup()`) — copiar el bloque tal cual de
  `tests/test_uuid_v2.py` o `tests/test_bulk_create.py`, no reinventarlo. Solo el primer archivo que se
  importa en cada worker de pytest aplica su configuración.
- Como los modelos de este repo son abstractos, cada test que necesita una tabla real define un modelo
  concreto "de usar y tirar" en el propio archivo y crea/borra la tabla con `connection.schema_editor()`
  en `setUpClass`/`tearDownClass` (no hay migraciones).
- Si el modelo usa `created_by`/`updated_by` (heredados de `UUIDModel`/`UUIDModelV2`), migrar
  `contenttypes` y `auth` primero (`call_command('migrate', 'contenttypes'|'auth', verbosity=0)`).
- Cualquier modelo concreto que herede de `BaseModel` (con safedelete) **debe** usar
  `django_general_utils.models.fields.ForeignKey`/`OneToOneField`, nunca los de `django.db.models` — el
  metaclass lo valida y lanza `TypeError` al definir la clase si no.
- `BaseModel` no puede usar el `app_label='tests'` genérico: su metaclass agrega `HistoricalRecords()`
  automáticamente, y `django-simple-history` necesita `apps.app_configs[app_label]` (un `AppConfig` real y
  registrado) para resolver el modelo histórico dinámico — `'tests'` no lo es, así que un `BaseModel`
  concreto con ese app_label explota con `KeyError: 'tests'` al definirse. Usar `app_label='auth'` (o
  cualquier otra app real de `INSTALLED_APPS`) en su lugar — ver `tests/test_relation_fields.py`.
  `UUIDModelV2`/`UUIDModelV3`/`BaseV2`/`BaseV3` no tienen este requisito, `app_label='tests'` funciona
  normal con ellos.
- Importar cualquier cosa bajo `django_general_utils.models.*` dispara la cadena completa de
  `models/__init__.py` (incluye `ArrayField`, que requiere `psycopg2` instalado, y `vector_field.py`, que
  requiere `numpy`) — ya están en `dependency-groups.test`, no hay que agregarlos de nuevo salvo que se
  rompa algo.

## Reglas de estilo

`docs/02-python-style.md` tiene las reglas completas (línea en blanco antes de bloques de control/`return`,
docstrings solo cuando el WHY no es obvio, etc.). Ruff (`select = ["E","F","I","B"]`) está configurado en
`pyproject.toml`, pero el código preexistente (fuera de `tests/`) **no está limpio** — no lo arregles de
paso salvo que te lo pidan explícitamente; limitate a que los archivos que vos toques/crees pasen
`ruff check`.

## `UUIDModelV3` y el comando `sync_id_as_code`

`models/uuid_v3.py::UUIDModelV3` hereda de `UUIDModelV2` y cambia dos cosas: `uuid` (la PK) usa un uuid7
propio (`utils/uuid7.py`, sin dependencia externa — Python `>=3.9` no tiene `uuid.uuid7` del stdlib, que
recién llega en 3.14) en vez de uuid4, y `id_as_code` pasa de `queryable_property` anotada en cada query a
`CharField` real con `db_index=True`. `Meta.ordering = ('-uuid',)` (no `-created_at`) porque con uuid7 la
PK ya es time-ordered — ordenar por ella reusa el índice de la PK en vez de pedir uno aparte.

`id_as_code` se puebla solo (creación individual, `id` preseteado, retry por colisión y `bulk_create`) vía
hooks no-op agregados a `UUIDModelV2` (`_on_id_assigned`/`_on_id_reset`/`_on_ids_assigned`, invocados justo
donde ya se resuelve `id` en `save()`/`_assign_auto_ids`) — así V3 no duplica el locking/retry de V2, solo
extiende esos hooks. Si tocás el flujo de asignación de `id` en `UUIDModelV2.save()`, revisar que los tres
hooks se sigan llamando en los mismos puntos.

`management/commands/sync_id_as_code.py` detecta filas cuyo `id_as_code` guardado ya no coincide con lo
que generarían el `_ID_AS_CODE_PREFIX_`/`_SUFFIX_`/`_LENGTH_` **actuales** de cada subclase concreta de
`UUIDModelV3`, y por cada app afectada escribe una migración de datos (`RunPython`) con esos valores
horneados como literales — no toca el esquema (eso lo sigue generando `makemigrations` normal). Usa
`apps.all_models` en vez de `apps.get_models()` para el discovery porque este repo registra modelos de
test con `app_label='tests'` sin una `AppConfig` real — `get_models()` los ignora silenciosamente.

Antes de consultar cada modelo, `handle()` llama a `id_as_code_column_exists(model)` (introspección real
contra la DB vía `connection.introspection.get_table_description`) y salta el modelo con un warning si la
tabla o la columna todavía no existen físicamente — reportado en producción (Postgres) primero como
`psycopg2.errors.UndefinedColumn` (columna sin migrar) y después, en un setup multi-tenant con
`django-tenants`, como `UndefinedTable` (la tabla del modelo directamente no existe en el schema contra el
que corre el comando). `id_as_code_column_exists` atrapa `django.db.Error` en general en vez de intentar
enumerar cada excepción específica por backend/setup — cualquier falla de introspección se trata igual
(saltar el modelo) — y hace `connection.close()` al capturarla, porque en Postgres una query fallida dentro
de una transacción abierta deja la conexión en estado "aborted": sin cerrarla, el próximo modelo chequeado
en el mismo `for` fallaría también aunque esté perfectamente migrado. Sin este guard, un solo modelo
sin migrar/fuera de schema tira abajo el comando entero (ni siquiera reporta el resto). Ver
`tests/test_sync_id_as_code_command.py::test_id_as_code_column_exists_*` (incluye
`_false_when_table_missing_entirely` y `_recovers_connection_for_later_models`) y
`test_handle_skips_model_missing_column_instead_of_crashing` — usan un helper (`_table_without_id_as_code_column`)
que recrea la tabla desde cero para simular el estado "sin migrar", porque tanto `ALTER TABLE ... DROP
COLUMN` (SQLite rechaza dropear una columna con índice) como `schema_editor.remove_field()` (para esta
composición de modelo puntual, el rebuild de tabla de SQLite no dropea la columna) resultaron poco
confiables para este caso de test.

## `BaseV2`/`BaseV3` (antes `BaseWithoutSafeDeleteModel`)

`models/base_without_safe_delete.py::BaseWithoutSafeDeleteModel` se renombró a `models/base_v2.py::BaseV2`
(mismo patrón que `UUIDModelV2`), y su manager `models/managers/base_without_safe_delete.py
::BaseWithoutSafeDeleteModelManager` se renombró a `models/managers/base_v2.py::BaseV2Manager`. El nombre
viejo sigue siendo la **misma clase** (`BaseWithoutSafeDeleteModel is BaseV2`) en los tres import paths que
un consumidor podría ya estar usando — `django_general_utils.models`, `.models.base_without_safe_delete` y
`.models.managers.base_without_safe_delete` — así que ningún import existente rompe. Código nuevo dentro de
este repo usa `BaseV2`/`BaseV2Manager`. `models/base_v3.py::BaseV3` es la versión nueva sobre
`UUIDModelV3` — reutiliza el mismo metaclass (`ModelBaseV2Meta`) y manager (`BaseV2Manager`) que `BaseV2`,
ninguno de los dos depende de qué `UUIDModelV*` se mezcle. `BaseV3.Meta.ordering` es `('-created_at',)`, NO
`('-uuid',)` — a propósito, pisa el default de `UUIDModelV3` (decisión explícita del usuario, confirmada,
no arreglar). Dos motivos: (1) un proyecto que migra `BaseV2` → `BaseV3` tiene filas viejas en `uuid4`
(aleatorio) conviviendo con filas nuevas en `uuid7` (time-ordered) — bajo `-uuid` las filas viejas
quedarían en orden efectivamente aleatorio; `-uuid` solo es correcto en un modelo que nace 100% en `uuid7`
sin datos heredados (por eso `UUIDModelV3` sí lo usa como default — no tiene ese baggage). (2) mantener el
ordering visible igual al de `BaseV2` para no romper el comportamiento de proyectos que ya migraron en
producción (gms-django ya lo hizo en todos sus modelos). Para que `-created_at` no pierda eficiencia frente
a `-uuid` (que reusa gratis el índice de la PK), `UUIDModelV2.created_at` tiene `db_index=True` explícito
— `AutoCreatedField` (`django-model-utils`) no indexa por default, así que sin esto `ORDER BY created_at
DESC` sería un sort completo en cada query. Ver `tests/test_uuid_v2.py::test_created_at_is_indexed`.

Ver `tests/test_base_v2_compat.py` (identidad de clase entre los import paths viejo/nuevo, modelo y
manager, más los deprecation warnings) y `tests/test_base_v3.py`.

Los tres shims (`models/__init__.py`, `models/base_without_safe_delete.py`,
`models/managers/base_without_safe_delete.py`) exponen el nombre viejo **solo** vía `__getattr__` a nivel
de módulo (PEP 562, helper compartido en `utils/deprecation.py::deprecated_alias`) — no como asignación
plana — para poder emitir un `DeprecationWarning` en cada acceso apuntando al nombre nuevo, sin dejar de
devolver la clase real. `pytest.ini` tiene `filterwarnings = ignore::DeprecationWarning` a nivel de
proyecto, así que un `pytest` normal no lo va a mostrar en el resumen — para verificar que dispara hay que
usar `self.assertWarns(DeprecationWarning)` (fuerza el filtro `always` en su propio contexto), como en
`tests/test_base_v2_compat.py::DeprecationWarningTests`.

Si en algún momento hay que renombrar otra clase pública de forma similar: mover el código al archivo
nuevo, y en el archivo viejo definir un `__getattr__(name)` que resuelva el nombre viejo vía
`deprecated_alias(obj_real, f'{__name__}.{name}', 'path.completo.al.nombre.nuevo')` y haga `raise
AttributeError` para cualquier otro nombre. Nunca usar una asignación plana (`NombreViejo = NombreNuevo`)
para el shim — con `__getattr__` sí se puede advertir en cada acceso; con asignación plana, no.

## Parche de `FieldTracker` para PKs con `uuid7` (`models/_field_tracker_patch.py`)

`model_utils.FieldTracker` (usado automáticamente por `ModelBaseMeta`/`ModelBaseV2Meta` en cualquier
modelo concreto, salvo que ya defina `tracker` a mano) decide si una instancia es "nueva" con
`not instance.pk`. Con una PK autoincremental eso es correcto (`pk` es `None` hasta el `INSERT`), pero con
`uuid7` como `default` de la PK (`BaseV2`/`BaseV3`) la instancia **ya tiene un `pk` truthy al construirse**
en memoria, antes de guardarse — el tracker terminaba tratando los valores recién construidos (los kwargs
del constructor) como si fueran el estado "guardado" en la base. Consecuencia concreta:
`CheckFlowStatusConstraint` (`models/constraints/check_flow_status.py`) usa
`instance.tracker.has_changed(field)` como primer gate de `validate()` — si un campo de estado se setea
**una sola vez**, en el constructor (`Modelo(status='X')`, patrón común vía `ModelForm`/`.create()`), y
nunca se toca de nuevo antes del primer `save()`, el tracker sin parchear reportaba `has_changed() ==
False` (comparaba contra su propia captura bogus, que coincide) — la constraint retornaba `None`
**sin llegar nunca** a validar `initial_statuses`. Con `initial_statuses` mal validado, un estado inicial
inválido pasaba en silencio.

El parche cambia `FieldInstanceTracker.set_saved_fields()` para usar `instance._state.adding` en vez de
`not instance.pk` — con una salvedad: `Model.from_db()` (usado por CUALQUIER carga vía queryset) llama a
`cls(*values)` (dispara `__init__`, donde `FieldTracker` inicializa su tracker) **antes** de corregir
`_state.adding = False` en la instancia resultante — así que sin compensar esto, toda fila cargada desde
la base perdería su snapshot (`has_changed()` reportaría `True` para todos los campos de cualquier
instancia recién leída, sin haber cambiado nada). Se compensa reinyectando `Model.from_db` a nivel de
`django.db.models.Model` (una sola vez, para que lo hereden todos los modelos sin tocar cada metaclase)
para volver a llamar `tracker.set_saved_fields()` justo después de que Django corrija `_state.adding`.

Se importa como side-effect desde `models/__init__.py` (`from . import _field_tracker_patch  # noqa: F401`)
— se aplica una sola vez, al importar el paquete, antes de que cualquier modelo real ejecute una query. Ver
`tests/test_field_tracker_patch.py` — usa el `FieldTracker` real de `model_utils` (no uno fake, a
diferencia de `tests/test_constraints_pure.py::CheckFlowStatusConstraintTests`) contra un modelo `BaseV3`
real, incluyendo el escenario end-to-end (`initial_statuses` rechazado incluso cuando el campo solo se
setea en el constructor) y el resync tras `from_db`.

## Guard `BaseModel` en `get_extra_restriction` (FK/O2O)

`fields/foreign_key.py::ForeignKey.get_extra_restriction` y
`fields/one_to_one.py::OneToOneField.get_extra_restriction` agregan un `IsNull(RawSQL('{alias}.deleted_at'
...))` para que los joins excluyan filas soft-deleted. Eso solo tiene sentido si **ambos** lados de la
relación son `BaseModel` (safedelete) — `BaseV2`/`BaseV3` no tienen columna `deleted_at`. Antes de este
guard, un `fields.ForeignKey`/`OneToOneField` desde o hacia un modelo `BaseV2`/`BaseV3` generaba SQL
referenciando una columna inexistente en ese lado de la relación. El guard chequea `self.model` (dueño del
campo) y `self.remote_field.model` (el destino) por separado — devuelve `None` (sin restricción) salvo que
los dos sean `BaseModel`. No se puede determinar desde acá si el join va en sentido directo o inverso
(Django invierte los alias al atravesar la relación en reversa), así que no alcanza con confiar en cuál de
los dos alias (`alias`/`related_alias`) es cuál. Ver `tests/test_relation_fields.py` — no necesita tablas
reales (`get_extra_restriction` solo arma una expresión SQL a partir del field estático, nunca ejecuta una
query), cubre las 4 combinaciones `BaseModel`↔`BaseV3` para FK y O2O.

## `register_model_signals` reconoce `BaseV3`

`models/base.py::register_model_signals` iteraba `issubclass(_model, (BaseModel, BaseWithoutSafeDeleteModel))`
para decidir si conectar los signals de `Meta.signals` de un modelo — un modelo concreto sobre `BaseV3` caía
al `else`, y aunque `assert issubclass(_model, models.Model)` pasaba igual (`BaseV3` es `models.Model`), sus
`Meta.signals` nunca se conectaban, en silencio. Ahora el tuple es `(BaseModel, BaseV2, BaseV3)` — usa
`BaseV2` (no `BaseWithoutSafeDeleteModel`) porque es un `import` local que se re-ejecuta en cada llamada a
la función; importar el nombre viejo dispararía el `DeprecationWarning` del shim en cada invocación, desde
dentro de la propia librería. Ver `tests/test_register_model_signals.py` — usa `mock.patch('django.apps.apps.get_app_config', ...)`
con un `_FakeAppConfig` en vez de un `AppConfig` real, porque el patrón `app_label='tests'` de este repo no
registra una app instalada de verdad (`apps.get_app_config('tests')` fallaría).

## `utils/drf/eager_loading.py` — select_related/prefetch_related/select_properties automáticos

Migrado desde un proyecto consumidor (GMS) tras validarlo ahí en 5 ViewSets/AjaxDatatableView reales,
encontrando y corrigiendo 4 bugs de N+1 ya en producción en el proceso. Expone:

- `build_eager_queryset(queryset, serializer_class, query=None)` — deriva `select_related`/
  `prefetch_related`/`select_properties` introspectando `serializer_class._declared_fields`. Solo
  reconoce relaciones declaradas como `NestedPrimaryKeyRelatedField`/`LazyRefSerializerField`
  (`utils/drf/fields/`) — un `PrimaryKeyRelatedField` implícito de DRF (pk-only) no necesita
  optimizarse: `use_pk_only_optimization()` devuelve `True` por default y nunca dispara una query
  extra por sí solo. `query` es un dict ya normalizado vía
  `django_restql.mixins.EagerLoadingMixin.get_dict_parsed_restql_query` (`None` = incluir todo).
- `AutoEagerLoadingMixin` — mixin de ViewSet. Sobreescribe `get_queryset()` para aplicar eager
  loading automáticamente sobre lo que resuelva `super().get_queryset()` (por eso debe ir **antes**
  de `GenericViewSet`/`mixins.*ModelMixin` en la herencia); expone `get_eager_queryset(qs)` para
  vistas con su propio `get_queryset()` (filtros de búsqueda, etc.) que solo necesitan aplicar el
  eager loading al final.
- `eager_relations_from_column_defs(model, column_defs)` + `AutoEagerLoadingAjaxDatatableMixin` —
  el mismo mecanismo para `django-ajax-datatable`, que no tiene serializer: deriva `select_related`
  de `get_column_defs()` (`foreign_field` o el `name` de la columna cuando coincide con el campo del
  modelo). Reusa `self.column_specs` (ya calculado por `initialize()` en `dispatch()`) en vez de
  volver a llamar `get_column_defs()` — llamarlo dos veces duplica sus propias queries de choices.

### Por qué no es 100% automático — dos escape hatches deliberados

`select_properties()` (queryable_properties) rechaza rutas con `relation_path` ("Cannot select
properties on related models.") — no hay forma de anotar un `@queryable_property` de un modelo
relacionado sobre un JOIN de `select_related`. Cuando el serializer/columna anidado necesita uno,
`build_eager_queryset` degrada esa relación de `select_related` a
`Prefetch(field, queryset=Modelo.objects.select_properties(...))` automáticamente — verificado que
`Prefetch` funciona igual sobre relaciones forward (to-one), no solo reverse/M2M, y que el annotate
cachea correctamente en la instancia anidada.

Para `AjaxDatatableView` este mismo caso **no se puede derivar** solo — no existe nada equivalente a
`Meta.fields` de un serializer que diga qué `@queryable_property` usa `customize_row()`. Se declara a
mano: `eager_loading_select_properties = {'relacion': ['propiedad']}`. Y como `get_column_defs()`
solo expone relaciones de columnas buscables/filtrables (`foreign_field` o nombre coincidente), una
relación usada en `customize_row()` sin columna propia (ej. `searchable: False` con un `name` que no
coincide con el campo real) es invisible — se declara con `eager_loading_relations = ['relacion']`.
Ambos son el mismo tipo de límite que un `SerializerMethodField`: código imperativo, no
introspectable — la diferencia es que estos dos sí son casos reales encontrados al migrar esto
(`tests/test_eager_loading.py` los cubre con datos, no solo la derivación en abstracto).

### Gotcha de testing encontrado acá: relaciones reversas y `app_label='tests'`

`tests/test_eager_loading.py` es el único archivo de este repo (al momento de escribirlo) que
necesita resolver una relación **reversa** por string (`Count('chapters', ...)`, `Prefetch('chapters',
...)`). Con `app_label='tests'` (el patrón usado en el resto del repo) esto falla en silencio con
`FieldError: Cannot resolve keyword 'chapters' into field` — `apps.get_models()` (que Django usa
internamente para construir el árbol de relaciones inversas de cada modelo) **ignora** los modelos
registrados bajo un `app_label` sin `AppConfig` real, exactamente la misma razón por la que
`sync_id_as_code` usa `apps.all_models` en vez de `apps.get_models()` (ver sección de ese comando más
arriba). El acceso Python directo (`libro.chapters.all()`) sigue funcionando igual — el descriptor lo
crea `ForeignKey.contribute_to_class` de forma síncrona — solo la resolución por **string** en el ORM
(`Count`, `.filter()`, `Prefetch` por nombre) se ve afectada. Solución: usar `app_label='auth'` (o
cualquier otra app real de `INSTALLED_APPS`) para cualquier modelo de test que necesite una relación
reversa resoluble por ORM — mismo fix que `test_relation_fields.py` ya usaba por una razón distinta
(`HistoricalRecords` de `BaseModel`). Aplica a cualquier futuro test de este repo con el mismo
requisito, no solo a `eager_loading`.

## `CheckModelRelationConstraint.create_sql()` — ya no devuelve `None` (Django 5+/`GeneratedField`)

`CheckModelRelationConstraint` no es un constraint real de DB — se valida en Python (`validate()`),
así que sus tres hooks de DDL (`constraint_sql`/`create_sql`/`remove_sql`) legítimamente no tienen
SQL que generar. Los tres devolvían `None`. Eso es seguro en casi todos los call sites de Django
porque filtran por truthiness antes de usarlo: `add_constraint()`/`remove_constraint()`
(`if sql: self.execute(sql)`) y la rama "sin params" de `table_sql()` (`", ".join(str(s) for s in
(...) if s)`).

**Excepción encontrada en Django 6.0.7** (consumidor real: gms-django agregando un campo
`GeneratedField(expression=SearchVector(...))` a un modelo que ya tenía
`CheckModelRelationConstraint` en `Meta.constraints`): `BaseDatabaseSchemaEditor.table_sql()` tiene
una segunda rama, activada cuando la tabla tiene **al menos una columna cuya definición requiere
parámetros propios** (un `GeneratedField`/`db_default`, ambos de Django 5.0+, con un literal
embebido en la expresión — ej. el `config='spanish'` de `SearchVector`). Esa rama hace:

```python
if params:
    for constraint in model._meta.constraints:
        self.deferred_sql.append(constraint.create_sql(model, self))  # sin filtrar por truthiness
```

Un `None` ahí queda tal cual en `deferred_sql`, y al ejecutarse (`BaseDatabaseSchemaEditor.execute()`
hace `sql = str(sql)`) se convierte en el string `'None'` — `ProgrammingError: syntax error at or
near "None"`. Solo se dispara al crear la tabla **desde cero** (`sync_apps`/`--no-migrations` de
pytest-django, o una migración `CreateModel` sobre una tabla nueva) en un modelo que combina ambos
ingredientes: una columna con parámetros propios + al menos un `CheckModelRelationConstraint`.

**Fix:** `create_sql()` devuelve `'SELECT 1'` (no-op válido en cualquier contexto DDL de Postgres/
cualquier backend) en vez de `None`. `constraint_sql()`/`remove_sql()` quedan sin cambios — sus call
sites sí filtran correctamente.

**Por qué no hay test de integración end-to-end para esto en este repo:** el campo (Django 4.2.30,
la versión que resuelve el `uv.lock` de este repo dentro del rango declarado `Django>=4.2.4,<=6.0.7`)
no tiene la rama vulnerable — su `table_sql()` solo conoce el camino `constraint_sql()` inline,
filtrado por truthiness, sin ninguna rama `if params:`/`deferred_sql.append(create_sql(...))` — y
tampoco existe `models.GeneratedField` antes de Django 5.0. Reproducir el escenario real requeriría
correr los tests contra Django 5+, lo que este repo no hace hoy (ver `pyproject.toml`/`uv.lock` para
la versión resuelta actual). `tests/test_constraints_pure.py::CheckModelRelationConstraintTests`
cubre el fix con tests puros (verifica el valor de retorno de cada hook), que sí corren en cualquier
versión de Django del rango soportado.

## Bugs conocidos — documentar con tests, no arreglar sin que se pida

Estos ya están confirmados leyendo el código fuente (no son sospechas). Si el usuario pide "agregar tests"
en general, documentarlos como comportamiento actual (`assert` sobre el bug, no sobre lo que "debería"
pasar) es más valioso que dejarlos pasar en silencio. Si el usuario pide explícitamente arreglarlos, recién
ahí tocar el código de producción.

- `utils/drf/validations/ids_in_query.py::ids_in_query` — solo chequea membership si
  `len(ids) != len(ids_available)`; con listas del mismo largo y cero overlap devuelve `[]` (sin errores).
- `utils/image/blur_img_to_base64.py::blur_img_to_base64` — el resultado de
  `img.filter(ImageFilter.GaussianBlur(...))` se descarta (no se reasigna a `img`), el blur nunca se aplica
  al output. Además `with_exception=True` (default) **suprime** excepciones (retorna el fallback);
  `with_exception=False` es lo que las re-lanza — el nombre del parámetro se lee al revés de lo que hace.
- `models/constraints/check_model_relation_constraint.py::CheckModelRelationConstraint.validate` —
  `check(instance)` debe devolver `False` para pasar; devolver `True` **o `None`** (p. ej. una función sin
  `return`) ambos disparan `ValidationError`.
- `models/constraints/check_editable_constraint.py::CheckEditableConstraint.__eq__` — referencia
  `CheckModelRelationConstraint`, que este módulo **nunca importa**. Comparar dos instancias con `==`
  lanza `NameError`, no solo "compara con la clase equivocada" (ver `tests/test_constraints_pure.py`).
- `models/constraints/check_max_rows_contraint.py::CheckRowsModelConstraint` y
  `check_max_rows_without_safe_delete_contraint.py::CheckRowsModelWithoutSafeDeleteConstraint` — con el
  default `check=None`, `Q(self.check)` envuelve un hijo `None` puro; al resolverlo, `Q(...).check(...)`
  lanza `TypeError` (no `FieldError`, así que el `except FieldError: pass` no lo atrapa). Es decir, **el
  uso más básico de estas constraints (sin pasar `check=`) rompe siempre** — hay que pasar explícitamente
  algo como `check=Q()` para evitarlo (ver `tests/test_db_backed.py`).
- `utils/drf/exception_handler.py::exception_handler` — para una `ValidationError` de Django "plana" (no
  `ListValidationError`), usa `exc.error_dict` directamente en vez de `exc.message_dict`. `error_dict`
  **no aplana** los mensajes: cada valor sigue siendo una lista de objetos `ValidationError` anidados, no
  strings — inconsistente con el camino de `ListValidationError.error_list` (que sí usa `message_dict`) y
  probablemente no serializa limpio a JSON en la respuesta de DRF.
- `models/managers/base.py::bulk_create_or_update_dict` — en el except de `bulk_update`, hace
  `zip(models_to_create, ...)` en vez de `zip(models_to_update, ...)`.
- `models/functions/random_number.py::RandomNumber.as_sqlite` — renderiza `'RAND'`, que no existe en
  SQLite (la función real es `RANDOM()`).
- `utils/forms/field/select.py::DataAttributesSelect.create_option` — hardcodea
  `subindex=None, attrs=None` al llamar a `super().create_option(...)`, descartando los argumentos reales
  recibidos. También tiene default mutable `data={}` en el constructor.
- `utils/drf/validations/fields.py::MinMaxElementsValidator` — el parámetro `required` del constructor se
  guarda pero nunca se usa en `__call__` (dead param); usa `assert` (no `ValidationError`) para validar
  configuración, así que se puede desactivar con `-O`.
- `utils/drf/middleware/token_auth_middleware_socket.py` — compara `token_name == prefix_token` donde
  `prefix_token` es una tupla (`AUTH_HEADER_TYPES`), casi seguro siempre `False`; y llama a
  `get_user_by_header(...)`/`get_user_by_query_params(...)` (ambas `@database_sync_to_async`) **sin
  `await`** en `QueryAuthMiddleware.__call__` — probablemente rompe en runtime siempre que se alcance esa
  rama. No tiene test en este repo (requiere infraestructura de Channels/JWT más pesada).
- `utils/drf/filters/postgres_search.py::PostgresSearchFilter` — el path de error de `search_version` no
  soportado referencia `self.search_version`, que nunca se asigna como atributo de instancia; en vez del
  `ValueError` esperado, lanza `AttributeError`.
- `safedelete/admin/safedelete.py::SafeDeleteAdmin` — la columna `is_deleted` en realidad retorna
  `obj.is_active` (nombre invertido); `get_queryset` decide mostrar soft-deleted vía substring-match sobre
  `request.path` (`'change' in path`/`'create' in path` — falsos positivos fáciles); usa un manager
  `self.model.filter` no estándar (no `.objects`).
- `views/create_view.py` / `views/update_view.py` — asumen que cualquier `ValidationError` capturado tiene
  `.error_dict`; una `ValidationError` con mensaje plano (no dict) hace que el propio handler lance
  `AttributeError` en vez de manejarlo. `utils/drf/exception_handler.py` sí protege esto con `hasattr`.

## Duplicación conocida (no consolidar sin que se pida)

- `models/signals.py` es un duplicado byte-a-byte de `SignalRegister`/`register_model_signals` en
  `models/base.py`, y no lo importa nadie más del repo — código muerto.
- `ModelBaseMeta._add_formated_number` (`models/base.py`) y `FormattedNumberField.contribute_to_class`
  (`models/fields/formated_number_field.py`) implementan lo mismo de forma independiente — un modelo con
  `BaseModel` + `fields.FloatField` termina con ambos mecanismos agregando los mismos métodos.
- `fields/one_to_one.py::OneToOneField.get_extra_restriction` y
  `fields/foreign_key.py::ForeignKey.get_extra_restriction` tienen el mismo cuerpo palabra por palabra.
- `constraints/check_max_rows_contraint.py` y `constraints/check_max_rows_without_safe_delete_contraint.py`
  son casi el mismo archivo salvo el filtro de `FIELD_NAME`.

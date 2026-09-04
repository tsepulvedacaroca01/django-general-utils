# 00 — Contexto de la librería

## Qué es este repositorio

`django-general-utils` es una librería/app de Django **instalable** (ver `pyproject.toml`), pensada para
ser consumida por otros proyectos Django — no es un proyecto con modelos de negocio propios. El paquete
se gestiona con **uv** (lock file `uv.lock`), no con `pip`/`setup.cfg`.

Todo lo que expone son mixins **abstractos**: `UUIDModel`, `UUIDModelV2`, `UUIDModelV3`, `BaseModel`,
`BaseV2`, `BaseV3`, managers/querysets custom, utils de DRF, helpers de factories, etc.
(`Meta.abstract = True` en todos los modelos base, ver `django_general_utils/models/`). No hay `Company`,
`Product`, viewsets, serializers ni services reales dentro de este repo — esos viven en los proyectos que
instalan la librería.

`BaseV2` se llamaba `BaseWithoutSafeDeleteModel` (vivía en `models/base_without_safe_delete.py`) — ese
módulo/nombre se mantienen como alias de compatibilidad (misma clase, no una copia) porque hay proyectos
consumidores que ya importan desde ahí. Código nuevo dentro de este repo (tests incluidos) usa `BaseV2`.

Requiere PostgreSQL en producción (usa `pg_advisory_xact_lock`, `ArrayField`, etc.), pero los tests corren
sobre sqlite en memoria: la lógica específica de Postgres se desactiva sola en ese entorno
(`connection.vendor != 'postgresql'` → no-op) y no se testea acá.

---

## Qué partes de `01-tests.md` y `02-python-style.md` aplican tal cual

- Estilo general (`02`): ruff, orden de imports, reglas de línea en blanco, regla de docstrings.
- Nota de `ValidationError` vs `IntegrityError` (`01`): `BaseModel`/`BaseV2`/`BaseV3` llaman `full_clean()`
  antes de guardar, igual que en el proyecto de origen de esas convenciones.
- `return None` explícito al final de cada test.

## Qué partes NO aplican (fueron escritas para un proyecto consumidor, ej. GMS)

- `factory_boy` + `pytest_factoryboy.register()`, fixtures `<algo>_factory` autogeneradas,
  `conftest.py` por app, `main.utils.tests.fixtures`, `request_factory`, `login`, `mock_user_create` —
  esos fixtures viven en el proyecto consumidor, no en esta librería.
- `TestViewSets` / `TestSerializers` / `TestServices` — este repo no tiene viewsets, serializers ni
  services propios que testear.
- `pytest.ini` con `DJANGO_SETTINGS_MODULE = main.settings` / `addopts = --no-migrations` — no aplica,
  acá no hay un settings module real para pytest-django (ver siguiente sección).
- La referencia a `docs/00-proyecto-gms.md` que aparece en `01-tests.md` (sección `ProductStock`) es de
  ese otro proyecto; no existe equivalente acá.

---

## Cómo se bootstrapea Django en los tests de esta librería

`pytest-django` **no está instalado**. `boot_django.py` no es un settings module válido para pytest — es
un helper que `makemigrations.py` y `migrate.py` invocan explícitamente
(`from boot_django import boot_django; boot_django()`). pytest lo ignora.

Cada archivo bajo `tests/` configura Django manualmente al importarse:

```python
if not settings.configured:
    settings.configure(
        BASE_DIR=...,
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=('django.contrib.auth', 'django.contrib.contenttypes'),
        TIME_ZONE='UTC',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.AutoField',
    )
    django.setup()
```

Solo el **primer** archivo que se importa en cada proceso/worker aplica esta configuración — el resto
hereda esa misma sesión de settings. Por eso todos los archivos deben copiar el mismo bloque tal cual, no
reinventarlo con valores distintos.

Como los modelos base son abstractos y no pertenecen a ningún app instalada, cada test define un modelo
concreto "de usar y tirar" dentro del propio archivo, y crea/borra su tabla manualmente con
`connection.schema_editor()` en `setUpClass`/`tearDownClass` — no hay migraciones ni `--no-migrations`
involucrados:

```python
class MyThrowawayModel(UUIDModelV2):  # o UUIDModelV3 / BaseV2 / BaseV3 / BaseModel
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        app_label = 'tests'
        db_table = 'test_my_throwaway_model'


class MyModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(MyThrowawayModel)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(MyThrowawayModel)
        super().tearDownClass()
```

Ver `tests/test_uuid_v2.py` y `tests/test_bulk_create.py` como plantilla.

**`BaseModel` es la excepción al patrón `app_label='tests'`**: su metaclass (`ModelBaseMeta`) agrega
`HistoricalRecords()` automáticamente, y `django-simple-history` necesita `apps.app_configs[app_label]` —
un `AppConfig` **real y registrado** — para resolver dónde poner el modelo histórico dinámico que genera.
`'tests'` no es una app instalada de verdad (es solo la convención de `app_label` que usan
`UUIDModelV2`/`UUIDModelV3`/`BaseV2`/`BaseV3`, que no tienen ese requisito), así que un `BaseModel`
concreto con `app_label='tests'` explota con `KeyError: 'tests'` al definirse. Usar `app_label='auth'` (o
cualquier otra app real ya en `INSTALLED_APPS`) en su lugar — Django no exige que el modelo pertenezca
lógicamente a esa app, solo que el label resuelva a un `AppConfig` real. Ver
`tests/test_relation_fields.py` (primer lugar del repo que definió un `BaseModel` concreto).

**Segunda razón, independiente de `BaseModel`, para necesitar `app_label='auth'`**: cualquier modelo
de test que necesite resolver una relación **reversa** por string en el ORM (`Count('related_name',
...)`, `.filter(related_name__x=...)`, `Prefetch('related_name', ...)`) falla en silencio con
`FieldError: Cannot resolve keyword '<related_name>' into field` bajo `app_label='tests'` —
`apps.get_models()` (que Django usa para construir el árbol de relaciones inversas de cada modelo)
ignora los modelos sin `AppConfig` real, la misma razón por la que `sync_id_as_code` usa
`apps.all_models` en vez de `apps.get_models()`. El acceso Python directo (`instancia.related_name.all()`)
sigue funcionando igual — el descriptor lo crea `ForeignKey.contribute_to_class` de forma síncrona —
solo la resolución por *string* se ve afectada. Mismo fix: `app_label='auth'`. Ver
`tests/test_eager_loading.py`, que necesita esto para su modelo `Book`/`Chapter` (`related_name='chapters'`).

Los `management/commands/` (ver `django_general_utils/management/commands/sync_id_as_code.py`) se testean
igual: sin invocar el comando completo contra un registro global de modelos (`apps.get_models()`/
`apps.all_models` verían también los modelos "de usar y tirar" de otros archivos de test si corren en el
mismo proceso), sino importando y testeando directamente las funciones puras que el comando expone a nivel
de módulo, contra el modelo concreto propio del archivo. Ver `tests/test_sync_id_as_code_command.py`.

Código de producción que necesita `apps.get_app_config(app_name)` (ej. `register_model_signals`) tiene el
mismo problema en sentido inverso: no hay una app real para pasarle. Se testea con
`mock.patch('django.apps.apps.get_app_config', return_value=_FakeAppConfig([...]))` — un doble mínimo con
un `.get_models()` que devuelve la lista de modelos "de usar y tirar" del test, en vez de intentar registrar
una `AppConfig` real. Ver `tests/test_register_model_signals.py`.

Si el modelo de prueba hereda `created_by`/`updated_by` (vienen de `UUIDModelV2`), hay que migrar
`contenttypes` y `auth` primero, porque esas FKs apuntan a `auth.User` por defecto:

```python
call_command('migrate', 'contenttypes', verbosity=0)
call_command('migrate', 'auth', verbosity=0)
```

Los tests hoy son `unittest.TestCase`, no clases pytest con inner classes (`TestFactories`,
`TestProperties`, etc.) — ese patrón de `01-tests.md` asume un modelo concreto real con una factory
registrada, algo que no existe en esta librería. Si en el futuro este repo gana modelos concretos reales
(por ejemplo tests de integración contra Postgres), ahí sí tiene sentido adoptar factories + inner
classes para esos casos puntuales.

---

## Gestión de dependencias con uv

Todo vive en `pyproject.toml` (`[project.dependencies]` para runtime, `[dependency-groups]` para dev/test)
más `uv.lock` (commiteado, fuente de verdad de versiones exactas). Ya no existen `setup.cfg`, `setup.py`,
`requirements.txt` ni `requirements-test.txt`.

- `dependency-groups.test` — `pytest`, `pytest-xdist`, `psycopg2-binary`. Este último es necesario
  únicamente para poder **importar** `django.contrib.postgres.fields.ArrayField` (se usa en
  `models/base.py`) — los tests no se conectan a un Postgres real, corren sobre sqlite.
- `dependency-groups.lint` — `ruff`, con su config en `[tool.ruff]` del mismo `pyproject.toml`.
- `dependency-groups.dev` — combina ambos (`{include-group = "test"}` + `{include-group = "lint"}`).

Dos cuidados al tocar `dependencies`:
- `numpy` está declarado explícito porque `models/fields/vector_field.py` hace `import numpy as np`
  directamente — con `pip` se colaba de rebote como transitiva de `pgvector`, pero `uv` no instala nada
  que no esté declarado, así que hay que listarlo a mano.
- Correr `uv run`/`uv sync` **dentro del contenedor** puede reescribir `uv.lock` (markers de resolución
  específicos de esa plataforma) sin que haya cambiado ninguna dependencia real — no es necesariamente un
  cambio a commitear. Revisar el diff (`git diff uv.lock`) y descartarlo (`git restore uv.lock`) si es solo
  ese ruido de plataforma.

Comandos típicos de uv (dentro del contenedor, o localmente si tenés `uv` instalado — pero ojo con la
siguiente sección, localmente no vas a poder *correr* los tests igual):

```bash
uv sync --group dev     # instala runtime + test + lint en el venv del proyecto
uv lock                 # recalcula uv.lock tras tocar [project.dependencies] o [dependency-groups]
uv run ruff check .     # lint
uv run pytest -n 6      # tests
```

## Cómo correr los tests

No hay forma de correr la suite fuera de Docker: paquetes como `ordered_model`, `queryable_properties`,
`model_utils` o `safedelete` no están instalados en el entorno local, solo dentro de la imagen (`uv sync`
corre en el `Dockerfile`, no en el host).

El `Dockerfile` usa `UV_PROJECT_ENVIRONMENT=/opt/venv` a propósito: `docker-compose.dev.yml` monta todo el
proyecto (`./:/usr/src/app`) encima del código copiado en el build, así que si el venv viviera dentro de
`/usr/src/app` (el default de `uv sync`, `.venv/`) el bind mount lo taparía. Al vivir en `/opt/venv` (fuera
del mount) sobrevive, y queda en el `PATH` del contenedor.

```bash
# Construir la imagen
docker-compose -f docker-compose.dev.yml build

# Correr toda la suite (igual que hace el contenedor por defecto: uv run pytest -n 6)
docker-compose -f docker-compose.dev.yml up --abort-on-container-exit

# Correr un archivo puntual, sin paralelismo (más fácil de debuggear)
docker-compose -f docker-compose.dev.yml run --rm app-django-django-general-utils-dev \
    bash -c "uv run pytest tests/test_bulk_create.py -v -p no:xdist"

# Lint
docker-compose -f docker-compose.dev.yml run --rm app-django-django-general-utils-dev \
    bash -c "uv run ruff check ."
```

`docker-compose run` reinstala el paquete local (`uv sync`) en cada invocación porque el bind mount pisa
`/usr/src/app` con el código actual — normalmente rápido (todo ya en el venv de `/opt/venv`), pero si la
red del host/Docker está caída, ese paso falla intentando resolver `build-system.requires` contra PyPI
aunque no haya cambiado ninguna dependencia real. Agregar `--no-sync` a `uv run` (`uv run --no-sync pytest
...` / `uv run --no-sync ruff check .`) salta ese paso y corre directo contra lo que ya está instalado en
`/opt/venv` — funciona sin red mientras no se haya tocado `pyproject.toml`/`uv.lock`.

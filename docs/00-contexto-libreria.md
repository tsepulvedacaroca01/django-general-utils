# 00 — Contexto de la librería

## Qué es este repositorio

`django-general-utils` es una librería/app de Django **instalable** (ver `pyproject.toml`), pensada para
ser consumida por otros proyectos Django — no es un proyecto con modelos de negocio propios. El paquete
se gestiona con **uv** (lock file `uv.lock`), no con `pip`/`setup.cfg`.

Todo lo que expone son mixins **abstractos**: `UUIDModelV2`, `BaseModel`, `BaseWithoutSafeDeleteModel`,
managers/querysets custom, utils de DRF, helpers de factories, etc. (`Meta.abstract = True` en los tres
modelos base, ver `django_general_utils/models/`). No hay `Company`, `Product`, viewsets, serializers ni
services reales dentro de este repo — esos viven en los proyectos que instalan la librería.

Requiere PostgreSQL en producción (usa `pg_advisory_xact_lock`, `ArrayField`, etc.), pero los tests corren
sobre sqlite en memoria: la lógica específica de Postgres se desactiva sola en ese entorno
(`connection.vendor != 'postgresql'` → no-op) y no se testea acá.

---

## Qué partes de `01-tests.md` y `02-python-style.md` aplican tal cual

- Estilo general (`02`): ruff, orden de imports, reglas de línea en blanco, regla de docstrings.
- Nota de `ValidationError` vs `IntegrityError` (`01`): `BaseModel`/`BaseWithoutSafeDeleteModel` llaman
  `full_clean()` antes de guardar, igual que en el proyecto de origen de esas convenciones.
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
class MyThrowawayModel(UUIDModelV2):  # o BaseWithoutSafeDeleteModel / BaseModel
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
- `Django` está acotado a `<5.0` (`Django>=4.2.4,<5.0`) porque `pytest.ini` filtra
  `django.utils.deprecation.RemovedInDjango50Warning`, una clase que Django 5.x eliminó — sin el techo,
  `uv lock` resuelve a la última versión disponible y la suite ni siquiera arranca. Si en algún momento
  se migra el proyecto a Django 5, hay que limpiar ese `filterwarnings` en `pytest.ini` primero.

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

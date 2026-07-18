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

# django-general-utils

Librería/app de Django con utilidades y abstracciones reutilizables entre proyectos: modelos base con
UUID + id numérico secuencial, campos y constraints custom, managers/querysets con `bulk_create`/`bulk_update`
"seguros", helpers de DRF (filtros, paginación, validaciones, campos anidados), formularios, factories de
test, y más. No es un proyecto Django en sí mismo — se instala como dependencia dentro de otro proyecto.

> Requiere **PostgreSQL** en producción. Varias piezas (`ArrayField`, búsqueda por trigramas/vector, las
> funciones de `models/functions/`) son específicas de Postgres y no funcionan sobre otros motores.

## Requisitos

- Python ≥ 3.9
- Django ≥ 4.2.4, < 5.0
- PostgreSQL (para los features Postgres-only mencionados arriba)

Ver `pyproject.toml` para la lista completa de dependencias.

## Instalación

El paquete se gestiona con [uv](https://docs.astral.sh/uv/). Para agregarlo a otro proyecto:

```bash
uv add "django-general-utils @ git+https://github.com/tsepulvedacaroca01/django-general-utils"
```

o con pip, apuntando al repositorio (no se publica en PyPI):

```bash
pip install "git+https://github.com/tsepulvedacaroca01/django-general-utils"
```

Agregar `'django_general_utils'` a `INSTALLED_APPS`.

## Estructura del paquete

```
django_general_utils/
├── models/              modelos abstractos, managers, querysets, campos y constraints custom
├── utils/               helpers de DRF, formularios, factories de test, formato, imágenes, etc.
├── templatetags/        tags de template genéricos
├── context_processors/  context processors genéricos
└── test/                helpers para tests (vacío por ahora)
```

Todo lo que expone `models/` son **mixins abstractos** (`Meta.abstract = True`) — este repo no define
modelos de negocio concretos; los proyectos consumidores heredan de estas clases.

## Modelos base

### `UUIDModel` (`models/uuid.py`)

Mixin abstracto con `uuid` (PK), `is_active`, `created_at`/`created_by`, `updated_at`/`updated_by`,
`stopped_at`. Expone `id_as_code` (código con padding tipo `VE-0000001`) y `next_code()` — depende de
`safedelete`'s `all_with_deleted()`, así que solo tiene sentido combinado con `BaseModel`.

### `UUIDModelV2` (`models/uuid_v2.py`)

Igual que `UUIDModel` pero con generación de `id` numérico secuencial **propia** (no depende de
`AutoField`/secuencias de la DB): usa un lock de Postgres (`pg_advisory_xact_lock`) + `MAX(id) + 1` dentro
de una transacción, con reintentos ante colisión. Puntos clave:

- **Punto de partida configurable**: sobrescribí `_INITIAL_ID_` (entero) o `get_initial_id()` (classmethod,
  para lógica dinámica — p. ej. resolver el punto de partida desde una consulta) en tu modelo concreto. Se
  usa únicamente cuando la tabla está vacía; con filas existentes siempre continúa desde `MAX(id) + 1`.
- **`bulk_create` también asigna `id`**: los querysets (`BaseModelWithoutSafeDeleteQuerySet`/
  `BaseModelQuerySet`) llaman a `_assign_auto_ids()` dentro de la misma transacción que el `INSERT`, así que
  `Model.objects.bulk_create([...])` funciona igual que `.save()` uno por uno.
- En SQLite el lock es un no-op (`connection.vendor != 'postgresql'`) — los tests corren igual, solo sin
  el lock real.

### `BaseModel` (`models/base.py`)

`SafeDeleteModel + OrderedModel + UUIDModel`, con soft-delete (`SOFT_DELETE_CASCADE`), historial
(`django-simple-history`, agregado automáticamente por el metaclass) y `FieldTracker` (`django-model-utils`,
también automático). Requiere usar los campos `fields.ForeignKey`/`fields.OneToOneField` de este mismo
paquete (no los de `django.db.models`) — el metaclass lo valida y lanza `TypeError` si no.

### `BaseWithoutSafeDeleteModel` (`models/base_without_safe_delete.py`)

Igual pero sobre `UUIDModelV2`, sin soft-delete. Agrega automáticamente métodos
`get_<campo>_format_decimal()` / `get_<campo>_format_currency()` (formato Babel, locale `es_CL` por
defecto) a cualquier campo numérico.

## Managers y querysets

Ambas familias (`base` con safedelete y `base_without_safe_delete` sin él) exponen:

- `bulk_create()` / `bulk_update()` — corren `full_clean()` por objeto antes de persistir (salvo
  `full_clean=False`), agregando errores como `ListValidationError` en vez de dejarlos pasar sueltos.
- `bulk_create_or_update_dict(values, update_fields, unique_fields, full_clean=True, delete_others=False)`
  — dado una lista de dicts, separa creación/actualización según `unique_fields`, corre `full_clean()` y
  hace `bulk_create`/`bulk_update`. `delete_others=True` borra filas no incluidas en `values`.

## Campos custom (`models/fields/`)

| Campo | Qué hace |
|---|---|
| `ForeignKey` / `OneToOneField` | Excluyen automáticamente relaciones hacia filas soft-deleted (salvo en `/admin/`) |
| `AdvancedCharField` | `to_upper`/`to_lower`/`to_title` (excluyentes) + `left_strip`/`right_strip`/`strip` en `get_prep_value` |
| `FloatField` / `IntegerField` / `PositiveIntegerField` | Igual que sus equivalentes de Django + métodos `get_<campo>_format_decimal/currency()` |
| `JSONSchemaField` | `JSONField` que valida contra un JSON Schema (`schema=<archivo>`, relativo al módulo del modelo) |
| `ChoiceArrayField` | `ArrayField` con `formfield()` como checkboxes — **Postgres-only** |
| `VectorField` | Wrapper de `pgvector.django.VectorField` — **Postgres-only** |

## Constraints custom (`models/constraints/`)

Todas heredan de `BaseConstraint`, que permite pasar `violation_error_message` como **dict** (`{campo:
mensaje}`) en vez de un string plano.

| Constraint | Uso |
|---|---|
| `UniqueConstraint` / `UniqueWithoutSafeDeleteConstraint` | Unicidad excluyendo (o no) filas soft-deleted; nombre autogenerado si no se pasa `name` |
| `CheckConstraint` / `CheckErrorConstraint` | Variantes de `CheckConstraint` con mensaje dict |
| `CheckEditableConstraint` | Impide editar ciertos campos tras la creación (usa `tracker.has_changed()`) |
| `CheckFlowStatusConstraint` | Máquina de estados: valida transiciones permitidas de un campo `choices` contra un dict `{estado: [siguientes]}` |
| `CheckModelRelationConstraint` | Valida una condición arbitraria (`check(instance)`) — ver nota abajo |
| `CheckRowsModelConstraint` / `CheckRowsModelWithoutSafeDeleteConstraint` | Límite máximo de filas que cumplen una condición |

> **Nota sobre `CheckModelRelationConstraint`**: `check(instance)` debe devolver `False` para pasar. Si
> devuelve `True` **o `None`** (p. ej. una función sin `return` explícito), se considera violación. No es
> la convención habitual de "`True` = válido" — ver `tests/test_constraints_pure.py`.

## Funciones de DB (`models/functions/`)

`ArrayAppend`, `ArrayToString`, `CleanHtml`, `FormattedDatetime`, `RandomNumber`, `SubqueryCount`,
`SubquerySum`, `WithChoices`, etc. — la mayoría son **Postgres-only** (usan `array_cat`, `regexp_replace`
con flags de Postgres, `to_char`, etc.).

## Utils destacados (`utils/`)

- **`is_valid_uuid`**, **`str_to_boolean`**, **`file_to_json`**, **`formats.format_currency/format_decimal`**
  (Babel) — funciones puras de propósito general.
- **`factory/`** — `DjangoModelFactory` (factory_boy) con `_get_or_create` que intenta `create()` primero
  y solo cae a `get()` ante `IntegrityError`; `to_dict()`/`generate_dict_factory()` para volcar un factory
  a dict sin tocar la DB (usa `.stub()`); `Provider` (Faker) con RUT chileno y coordenadas de Santiago.
- **`drf/`** — parser multipart anidado, paginación con `object_query`, filtros (`BackendFilter`,
  `OrFilter`, `OrderingFilter` con orden aleatorio, `PostgresSearchFilter`), campos (`PrimaryKeyRelatedField`
  con `only_pk`, `NestedPrimaryKeyRelatedField`, `LazyRefSerializerField`), validaciones
  (`MinMaxElementsValidator`, `ids_in_query`, `unique_fields`, `validate_unique_together`),
  `exception_handler` para convertir `ValidationError`/`ListValidationError` en `400`.
- **`postgres/`** — búsqueda combinando trigramas + full-text search + `icontains`/`istartswith` con
  ranking — **Postgres-only** (`pg_trgm`).
- **`forms/`** — `ModelForm` que separa miles/decimales según `settings.THOUSAND_SEPARATOR`/
  `DECIMAL_SEPARATOR` y widget `DataAttributesSelect` para inyectar `data-*` a los `<option>`.
- **`image/blur_img_to_base64`** — genera un thumbnail borroso en base64 (BMP) con fallback silencioso.
- **`safedelete/admin`**, **`ajax_datatable/`**, **`drf_spectacular/`**, **`rest_ql/`** — integraciones con
  esos paquetes (admin con soft-delete + historial, datatables con búsqueda Postgres, generación de
  schema OpenAPI, campos dinámicos por query).

Varias de estas piezas tienen comportamientos no obvios (parámetros invertidos, convenciones poco
intuitivas, algún bug conocido) — están documentados con tests específicos en `tests/` y en `CLAUDE.md`.

## Templatetags (`templatetags/`)

- `{% dict_get d key default=None %}` — `d.get(key, default)`.
- `{% call_method obj "nombre_metodo" arg1 kw=val %}` — invoca un método del objeto desde el template.

## Context processors (`context_processors/`)

- `export_envs` — agrega `{'ENV': os.environ}` al contexto de todos los templates.

## Desarrollo

Ver `docs/00-contexto-libreria.md` para el contexto completo (por qué esta librería se testea distinto a
un proyecto Django normal) y `docs/01-tests.md` / `docs/02-python-style.md` para convenciones de tests y
estilo. Resumen rápido:

```bash
# Construir la imagen de desarrollo
docker-compose -f docker-compose.dev.yml build

# Correr toda la suite de tests
docker-compose -f docker-compose.dev.yml up --abort-on-container-exit

# Lint
docker-compose -f docker-compose.dev.yml run --rm app-django-django-general-utils-dev \
    bash -c "uv run ruff check ."
```

## Licencia

MIT

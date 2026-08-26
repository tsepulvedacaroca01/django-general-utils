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
├── management/commands/ management commands (ver Management commands)
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

### `UUIDModelV3` (`models/uuid_v3.py`)

Igual que `UUIDModelV2`, con dos cambios:

- **`uuid` (la PK) usa uuid7** (`utils/uuid7.py` — implementación propia, sin dependencia externa, porque
  `uuid.uuid7` del stdlib recién existe en Python 3.14 y este paquete soporta `>=3.9`) en vez de uuid4.
  Al ser time-ordered (48 bits de timestamp Unix en ms + versión + random), los inserts en el índice de la
  PK son secuenciales en vez de aleatorios — mejor locality/menos fragmentación de índice con volumen alto.
  Por eso `Meta.ordering = ('-uuid',)` en vez de `-created_at`: ordenar por la PK reusa su propio índice en
  vez de requerir uno aparte para `created_at`.
- **`id_as_code` es una columna real** (`CharField`, `db_index=True`), no una `queryable_property`
  anotada en cada query como en `UUIDModelV2`/`UUIDModel`. Se puebla **automáticamente** dondequiera que se
  resuelve `id` — creación individual (`.save()`), `id` preseteado a mano, retry ante colisión de `id`, y
  `bulk_create()` — así que no hay que llamar nada a mano en el flujo normal.

Si cambiás `_ID_AS_CODE_PREFIX_`/`_ID_AS_CODE_SUFFIX_`/`_ID_AS_CODE_LENGTH_` en un modelo concreto después
de tener filas existentes, esas filas quedan con el `id_as_code` viejo — correr el comando
`sync_id_as_code` (ver [Management commands](#management-commands)) para generar la migración de datos que
las actualiza.

### `BaseModel` (`models/base.py`)

`SafeDeleteModel + OrderedModel + UUIDModel`, con soft-delete (`SOFT_DELETE_CASCADE`), historial
(`django-simple-history`, agregado automáticamente por el metaclass) y `FieldTracker` (`django-model-utils`,
también automático). Requiere usar los campos `fields.ForeignKey`/`fields.OneToOneField` de este mismo
paquete (no los de `django.db.models`) — el metaclass lo valida y lanza `TypeError` si no.

### `BaseV2` (`models/base_v2.py`)

Igual que `BaseModel` pero sobre `UUIDModelV2`, sin soft-delete. Agrega automáticamente métodos
`get_<campo>_format_decimal()` / `get_<campo>_format_currency()` (formato Babel, locale `es_CL` por
defecto) a cualquier campo numérico.

> **Nombre anterior**: esta clase se llamaba `BaseWithoutSafeDeleteModel` (`models/base_without_safe_delete.py`)
> y su manager se llamaba `BaseWithoutSafeDeleteModelManager`
> (`models/managers/base_without_safe_delete.py`). Ambos módulos/nombres siguen funcionando — quedaron como
> shims de compatibilidad que re-exportan las clases reales (`BaseWithoutSafeDeleteModel is BaseV2`,
> `BaseWithoutSafeDeleteModelManager is BaseV2Manager` — misma clase, no una copia), así que el código
> existente que los usa **no necesita cambios de código**. Sí van a empezar a ver un
> `DeprecationWarning` al importarlos (`'...BaseWithoutSafeDeleteModel' is deprecated ... use
> '...BaseV2' instead`) — es solo un aviso, nada se rompe. Python ignora `DeprecationWarning` por
> default fuera de `__main__`, así que puede no imprimirse salvo que el proyecto consumidor corra
> con `python -W default::DeprecationWarning` o tenga algo como `warnings.simplefilter('always',
> DeprecationWarning)`/`filterwarnings = always::DeprecationWarning` (pytest) configurado. Para
> código nuevo, usar `BaseV2`/`BaseV2Manager` directamente.

### `BaseV3` (`models/base_v3.py`)

Igual que `BaseV2` pero sobre `UUIDModelV3` en vez de `UUIDModelV2` — hereda uuid7 e `id_as_code` como
columna real de esa sección. Reutiliza el mismo metaclass (`ModelBaseV2Meta`) y el mismo manager
(`BaseV2Manager`, `models/managers/base_v2.py`) que `BaseV2` — ninguno de los dos depende de qué
`UUIDModelV*` se mezcle. No tiene nombre anterior; es la clase nueva de esta sesión.

> **`ordering` es `-created_at`, no `-uuid`** — a diferencia de `UUIDModelV3` (que sí usa `-uuid` por
> default). Hay dos razones, no solo compatibilidad de API:
> - Los proyectos que migran de `BaseV2` a `BaseV3` típicamente tienen filas viejas con PK `uuid4`
>   (aleatoria) conviviendo con filas nuevas en `uuid7` (time-ordered) — bajo `-uuid`, las filas viejas
>   quedan en un orden efectivamente aleatorio (uuid4 no codifica tiempo), aunque las nuevas sí ordenen
>   bien; solo tiene sentido ordenar por `-uuid` en un modelo que nace 100% en `uuid7`, sin datos
>   heredados. `-created_at` es correcto para ambos casos por igual.
> - Cambiar el default silenciosamente al pisar `BaseV2` → `BaseV3` también sería una regresión de
>   comportamiento visible (API, listados) para quien ya consume esos endpoints.
>
> `created_at` (`UUIDModelV2`, heredado por `UUIDModelV3`/`BaseV3`) tiene `db_index=True` explícito —
> sin eso, `AutoCreatedField` no indexa la columna por default y `ORDER BY created_at DESC` sería un sort
> completo en cada query. Con el índice, `-created_at` es prácticamente tan eficiente como `-uuid` (que
> reusa el índice de la propia PK) sin el problema de correctitud del punto anterior.

> Si tu modelo concreto define su propio `Meta`, tiene que heredar del `Meta` de `BaseV2`/`BaseV3`
> (`class Meta(BaseV3.Meta): ...`) para conservar el `ordering` — Django no combina automáticamente el
> `Meta` de una clase abstracta con un `Meta` nuevo que no lo subclasea.

> **`FieldTracker` y PKs `uuid7`**: el paquete parchea `model_utils.FieldTracker` al importarse
> (`models/_field_tracker_patch.py`) para que distinga correctamente instancias nuevas de instancias
> cargadas desde la base cuando la PK ya viene asignada al construirse en memoria (como `uuid7` en
> `BaseV2`/`BaseV3`) — sin el parche, `tracker.has_changed()`/`tracker.previous()` daban resultados
> incorrectos para instancias recién construidas (afecta directamente a `CheckFlowStatusConstraint`, que
> depende de eso para distinguir el estado inicial de una transición). Se aplica automáticamente, no
> requiere nada del lado del proyecto consumidor.

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
| `ForeignKey` / `OneToOneField` | Excluyen automáticamente relaciones hacia filas soft-deleted (salvo en `/admin/`) — solo cuando **ambos lados** de la relación son `BaseModel`; usarlos entre modelos `BaseV2`/`BaseV3` (sin `deleted_at`) funciona igual pero sin esa restricción |
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

## Management commands

### `sync_id_as_code`

Detecta, para cada subclase concreta de `UUIDModelV3` instalada en el proyecto consumidor, filas cuyo
`id_as_code` guardado ya no coincide con lo que generarían el `_ID_AS_CODE_PREFIX_`/`_ID_AS_CODE_SUFFIX_`/
`_ID_AS_CODE_LENGTH_` **actuales** del modelo (prefijo/sufijo cambiado, o filas nunca backfilleadas tras
agregar la columna). No es un reemplazo de `makemigrations` — no toca el esquema, solo genera una
**migración de datos** (`RunPython`) por cada app afectada, con el prefijo/sufijo/length horneados como
literales en el archivo generado.

```bash
# Reporta qué modelos tienen id_as_code desincronizado y termina con error si hay alguno (para CI)
python manage.py sync_id_as_code --check

# Genera la(s) migración(es) de datos correspondientes
python manage.py sync_id_as_code
python manage.py migrate
```

Flujo típico al cambiar `_ID_AS_CODE_PREFIX_`/`_SUFFIX_`/`_LENGTH_` de un modelo (o al agregar `id_as_code`
por primera vez sobre una tabla con filas existentes):

1. `python manage.py makemigrations` — si `id_as_code` es un campo nuevo, esto genera la migración de
   esquema (agregar la columna). No hace falta si el campo ya existía y solo cambió el prefijo/sufijo.
2. `python manage.py migrate` — aplica el esquema. **Este paso es obligatorio antes que `sync_id_as_code`**:
   la tabla/columna tiene que existir físicamente antes de poder consultarla/actualizarla — si un modelo
   sobre `UUIDModelV3` (o `BaseV3`) todavía no tiene esta migración aplicada en la base/schema donde corrés
   el comando (incluye setups multi-tenant tipo `django-tenants`, donde el comando puede estar corriendo
   contra un schema donde ese modelo ni siquiera tiene tabla), `sync_id_as_code` lo salta con un aviso en
   vez de fallar para el resto de modelos.
3. `python manage.py sync_id_as_code` — detecta el drift y genera la migración de datos.
4. `python manage.py migrate` — backfillea `id_as_code` para las filas afectadas.

#### Uso con `django-tenants`

`sync_id_as_code` no sabe nada de tenants — solo mira la conexión/schema actual. En un proyecto con
`django-tenants`, cada schema (el `public` compartido y cada tenant) tiene su propio subconjunto de tablas
visibles, así que hay que recorrerlos explícitamente con los comandos que ya trae `django-tenants`:
`tenant_command`/`all_tenants_command` (correr un comando en un schema puntual o en todos, ver [su
documentación](https://django-tenants.readthedocs.io/en/latest/use.html)).

**1. Migrar el esquema en todos lados primero** (siempre antes de `sync_id_as_code` — ver el paso 2 de
arriba):

```bash
python manage.py migrate_schemas --shared   # aplica el esquema en public (SHARED_APPS)
python manage.py migrate_schemas            # aplica el esquema en cada tenant (TENANT_APPS)
```

**2. Revisar drift en todos lados** (`--check`, informativo, no escribe nada):

```bash
python manage.py sync_id_as_code --check                    # apps de public (SHARED_APPS)
python manage.py all_tenants_command sync_id_as_code --check  # apps de cada tenant (TENANT_APPS)
```

**3. Generar las migraciones de datos — a mano, corriendo el modo escritura (sin `--check`) UNA sola vez
por schema representativo**, no con `all_tenants_command` en un solo paso:

```bash
python manage.py sync_id_as_code                              # apps de public, si el check de arriba mostró drift ahí
python manage.py tenant_command sync_id_as_code --schema=<un_tenant_con_drift>
```

> ⚠️ **Por qué no `all_tenants_command sync_id_as_code` (sin `--check`) directo**: el archivo de migración
> generado (`NNNN_sync_id_as_code.py`) no depende del contenido de un tenant en particular — el
> `RunPython` que escribe recalcula `id_as_code` a partir de `id` con el prefijo/sufijo/length actuales, y
> corre igual sea cual sea el schema donde después se aplique con `migrate`. Si corrés el modo escritura
> tenant por tenant con `all_tenants_command`, cada tenant que todavía muestre drift para la misma app va a
> generar **otro** archivo de migración para esa app (`0001_sync_id_as_code.py`, `0002_sync_id_as_code.py`,
> ...) — funcionalmente inofensivo (cada uno vuelve a aplicar el mismo cálculo, idempotente) pero deja
> migraciones redundantes en el historial. Alcanza con generarla una vez por app, contra **cualquier**
> schema donde ese modelo tenga al menos una fila con drift — no hace falta que sea el mismo tenant para
> todas las apps: si `organization.Company` solo muestra drift en `tenant_a` e `inventory.Product` solo en
> `tenant_b`, corré el paso 3 una vez contra cada uno. Revisá `git status` después de cada corrida — si no
> aparece ningún archivo nuevo, ya no queda nada por generar.

**4. Aplicar las migraciones de datos generadas, en todos lados:**

```bash
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
```

## Funciones de DB (`models/functions/`)

`ArrayAppend`, `ArrayToString`, `CleanHtml`, `FormattedDatetime`, `RandomNumber`, `SubqueryCount`,
`SubquerySum`, `WithChoices`, etc. — la mayoría son **Postgres-only** (usan `array_cat`, `regexp_replace`
con flags de Postgres, `to_char`, etc.).

## Utils destacados (`utils/`)

- **`is_valid_uuid`**, **`str_to_boolean`**, **`file_to_json`**, **`formats.format_currency/format_decimal`**
  (Babel), **`uuid7`** (generador UUIDv7 propio, sin dependencias — usado como `default` de `UUIDModelV3.uuid`)
  — funciones puras de propósito general.
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

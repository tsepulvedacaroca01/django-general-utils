# Tests — Convenciones del proyecto

## Stack

- **pytest** + **pytest-django** — runner principal
- **factory_boy** + **pytest-factoryboy** — generación de fixtures
- **Faker** + providers custom — datos falsos
- `DjangoModelFactory` de `django_general_utils.utils.factory.django`

---

## Configuración (`pytest.ini`)

```ini
[pytest]
DJANGO_SETTINGS_MODULE = main.settings
python_files = tests/*.py
addopts = --no-migrations
```

`--no-migrations` acelera los tests creando las tablas directamente desde los modelos.

---

## Fixtures globales (`main/utils/tests/fixtures.py`)

El `conftest.py` raíz lo carga con:

```python
# conftest.py (raíz del proyecto)
pytest_plugins = ['main.utils.tests.fixtures']
```

Fixtures disponibles en todos los tests:

| Fixture | Tipo | Descripción |
|---|---|---|
| `request_factory` | `_AuthRequestFactory` | Factory de requests autenticados: `.get()`, `.post()`, `.patch()`, `.delete()`; `auth_user=None` para anónimo |
| `json_to_form_data` | función | Convierte un dict JSON a multipart form data |
| `json_to_dict` | función | Convierte JSON renderizado de vuelta a dict Python |
| `mock_user_create` | autouse, session | Crea un usuario `admin` y activa `GlobalRequest` — requerido por `BaseV2` para `created_by` |
| `login` | function | `(APIClient, User)` — cliente DRF autenticado con JWT; requiere `register(UserFactory)` en el conftest de la app |
| `render` | function | Fuerza `.render()` en `TemplateResponse` antes de inspeccionar; no-op para JSON |

---

## Estructura de archivos por app

```
<app>/
  factories/
    __init__.py          → re-exporta todas las factories
    <modelo>.py          → definición de la factory
  tests/
    __init__.py
    conftest.py          → registra factories con pytest_factoryboy
    models/
      __init__.py
      <modelo>.py        → tests del modelo
    serializers/
      __init__.py
      <modelo>.py        → tests del serializer
    services/
      conftest.py        → mocks de sesión del servicio (opcional)
      <servicio>.py      → tests del service
    viewsets/
      __init__.py
      <modelo>.py        → tests del viewset
```

---

## Factories (`<app>/factories/<modelo>.py`)

```python
import factory.fuzzy
from django_general_utils.utils.factory import Provider
from django_general_utils.utils.factory.django import DjangoModelFactory
from faker import Faker

from main.utils.factory.provider import Provider as BaseProvider

fake = Faker('es_CL')
fake.add_provider(Provider)
fake.add_provider(BaseProvider)


class CompanyFactory(DjangoModelFactory):
    # Campos únicos: factory.Sequence garantiza unicidad entre llamadas
    dni = factory.Sequence(lambda n: fake.rut())
    business_name = factory.Sequence(lambda n: fake.company())

    # Campos no únicos: factory.LazyFunction es suficiente
    short_description = factory.LazyFunction(lambda: fake.company_short_description())

    # Archivos
    image = DjangoFile(open(fake.company_avatar(), mode="rb"), name="img.png")

    class Meta:
        model = "organization.Company"   # string 'app.Model', no la clase directa
        django_get_or_create = (
            "tab",
            "dni",
            "business_name",
            # todos los campos que forman la unicidad del objeto
        )
```

### Reglas de factories

- `Meta.model` siempre es un **string** `'app.Model'`, nunca la clase importada directamente.
- `Meta.django_get_or_create` lista todos los campos que identifican unívocamente al objeto.
- Campos únicos con lógica de colisión (ej. RUT que ya existe en la DB) → función auxiliar con `while` que reintenta:

```python
def random_dni():
    from organization.models import Company
    dni = fake.rut()
    while Company.objects.filter(dni=dni).exists():
        dni = fake.rut()
    return dni
```

- Cuando el modelo requiere lógica antes de `save()` (ej. hashear contraseña, verificar unicidad en DB):

```python
@classmethod
def _create(cls, model_class, *args, **kwargs):
    kwargs['password'] = make_password(kwargs['password'])
    while User.objects.filter(username=kwargs['username']).exists():
        kwargs['username'] = fake.user_rut()
    return super()._create(model_class, *args, **kwargs)
```

- Relaciones M2M se manejan con `@factory.post_generation`.

### `factories/__init__.py`

Re-exporta todo para que `conftest.py` importe desde un solo punto:

```python
from .company import CompanyFactory
```

---

## conftest.py por app

Usa `pytest_factoryboy.register()` para exponer cada factory como fixture de pytest:

```python
from pytest_factoryboy import register

from authentication.factories import UserFactory
from organization import factories

register(factories.CompanyFactory)   # → fixture: company_factory
register(UserFactory)                # → fixture: user_factory
```

`register(XxxFactory)` genera automáticamente:
- `xxx_factory` — callable que crea instancias (`xxx_factory()`)
- `xxx` — instancia ya creada (singleton por test)

### Registrar factories de otra app

Si los tests de una app necesitan una factory de otra app (más allá de `UserFactory`, que ya sigue este patrón), se importa directamente y se registra igual que las propias — al final, después de las factories locales:

```python
from pytest_factoryboy import register

from authentication.factories import UserFactory
from inventory.factories import LocationFactory, ProductStockFactory
from sale import factories

register(factories.CartFactory)
register(factories.CartProductFactory)
# ...
register(UserFactory)
register(LocationFactory)
register(ProductStockFactory)
```

No usar un `import ... as` con namespace para esto — importar la(s) factory(s) puntual(es) que se necesitan, igual que `UserFactory`.

---

## Tests de modelos (`<app>/tests/models/<modelo>.py`)

### Estructura general

```python
import pytest
from django.core.exceptions import ValidationError

from inventory.models import Income


@pytest.mark.django_db
class TestIncomeModel:

    class TestFactories: ...
    class TestConstraints: ...
    class TestProperties: ...
    class TestMethods: ...
    class TestSignals: ...
```

Reglas de estructura:

- `@pytest.mark.django_db` va **solo** en la clase raíz, no en las inner classes ni en los métodos.
- Las inner classes agrupan tests por **categoría semántica** (ver tabla abajo).
- Solo se incluye una inner class si el modelo tiene algo que testear en esa categoría — no crear clases vacías.
- Todos los métodos retornan `None` explícitamente (`return None`).
- Los métodos reciben las factories como argumento y las invocan como callable: `income_factory()`.
- Se pueden pasar overrides: `income_factory(number='INC-999')`.

### Inner classes y cuándo usarlas

| Inner class | Cuándo incluirla | Qué testea |
|---|---|---|
| `TestFactories` | Siempre | Que la factory crea instancias válidas; overrides de campos; subfactories |
| `TestConstraints` | Si el modelo tiene `UniqueConstraint`, `CheckConstraint` o `unique=True` | Que violar la restricción lanza `ValidationError` (ver nota abajo) |
| `TestProperties` | Si el modelo tiene cualquier tipo de property | Que la propiedad retorna el valor correcto (ver detalle abajo) |
| `TestMethods` | Si el modelo define cualquier método | Que cada método produce el resultado o efecto esperado — incluye `__str__` |
| `TestSignals` | Si `Meta.signals` registra señales | Que el signal dispara el callback y produce el efecto esperado |
| `TestQuerySets` | Si el modelo tiene un QuerySet custom con métodos de filtro | Que cada método devuelve exactamente los registros correctos y excluye los que no corresponden |
| `TestUseCases` | Si el modelo tiene flujos de negocio que combinan múltiples operaciones | Escenarios completos de negocio: secuencias de acciones y sus efectos acumulados sobre el estado |

---

### Subgrupos dentro de inner classes

Cuando cualquier inner class agrupa tests de **múltiples sub-temas distintos**, y cada uno tiene varios tests relacionados, se crea una **inner class anidada** (subgrupo) para cada sub-tema. Esto aplica a cualquier nivel: `TestProperties`, `TestMethods`, `TestQuerySets`, `TestSignals`, `TestValidate`, `TestGetters`, etc.

```python
@pytest.mark.django_db
class TestSaleModel:

    class TestProperties:
        # Sub-tema con pocos tests → tests directos
        def test_has_work_order_true(self, sale_factory, work_order_factory) -> None:
            ...

        def test_has_work_order_false(self, sale_factory) -> None:
            ...

        # Sub-tema con varios escenarios → subgrupo
        class TestCurrentStatus:
            def test_returns_none_when_no_status(self, sale_factory) -> None:
                ...

            def test_returns_status_name(self, sale_factory, sale_status_factory) -> None:
                ...

            def test_filterable_by_status(self, sale_factory, sale_status_factory) -> None:
                ...

    class TestMethods:
        # Un método simple → test directo
        def test_str_returns_code(self, sale_factory) -> None:
            ...

        # Un método con múltiples ramas/escenarios → subgrupo
        class TestDispatch:
            def test_creates_work_order(self, sale_factory) -> None:
                ...

            def test_raises_if_work_order_already_exists(self, sale_factory) -> None:
                ...

            def test_creates_dispatch(self, sale_factory) -> None:
                ...

    class TestQuerySets:
        # Método de queryset con múltiples casos → subgrupo
        class TestForStatus:
            def test_includes_matching_status(self, sale_factory, sale_status_factory) -> None:
                ...

            def test_excludes_other_status(self, sale_factory, sale_status_factory) -> None:
                ...
```

**Reglas de subgrupos:**

- `@pytest.mark.django_db` va **solo** en la clase raíz — se propaga a todos los niveles anidados automáticamente. No repetirlo en subgrupos.
- Los nombres siguen el mismo patrón `Test<NombreSubTema>`.
- Cuando hay múltiples sub-temas en la misma inner class sin subgrupo, usar separadores de comentarios para agruparlos visualmente:

```python
class TestProperties:
    # ------------------------------------------------------------------
    # is_active
    # ------------------------------------------------------------------

    def test_is_active_true_by_default(self, sale_factory) -> None:
        ...

    def test_is_active_false_after_cancel(self, sale_factory) -> None:
        ...

    # ------------------------------------------------------------------
    # total_amount
    # ------------------------------------------------------------------

    def test_total_amount_sums_products(self, sale_factory, sale_product_factory) -> None:
        ...
```

**Cuándo usar subgrupo vs separadores:**

| Situación | Convención |
|---|---|
| 1-3 tests para el sub-tema | Separador de comentario `# ---` |
| 4+ tests, o escenarios claramente distintos | Subgrupo `class Test<SubTema>:` |
| Múltiples variantes de un valor (ej. varios choices de un campo) | Subgrupo con `@pytest.mark.parametrize` dentro |

---

### Nota crítica: `ValidationError`, no `IntegrityError`

`BaseV2.save()` llama `full_clean()` automáticamente. Esto valida constraints a nivel de modelo **antes** de llegar a la base de datos, por lo que los tests de unicidad deben esperar `ValidationError` de `django.core.exceptions`, no `IntegrityError` de `django.db`.

```python
# INCORRECTO
from django.db import IntegrityError
with pytest.raises(IntegrityError): ...

# CORRECTO
from django.core.exceptions import ValidationError
with pytest.raises(ValidationError): ...
```

---

### TestFactories

```python
class TestFactories:
    def test_default(self, income_factory) -> None:
        instance = income_factory()
        assert isinstance(instance, Income)

        return None

    def test_with_warehouse(self, warehouse_factory, income_factory) -> None:
        warehouse = warehouse_factory()
        instance = income_factory(warehouse=warehouse)
        assert instance.warehouse == warehouse

        return None
```

- `test_default` verifica que la factory produce una instancia del tipo correcto.
- Tests adicionales verifican overrides de campos o subfactories.

---

### TestConstraints

```python
class TestConstraints:
    def test_unique_code_per_warehouse(self, warehouse_factory) -> None:
        from inventory.models import Location

        warehouse = warehouse_factory()
        Location.objects.create(warehouse=warehouse, code='DUP-01')

        with pytest.raises(ValidationError):
            Location.objects.create(warehouse=warehouse, code='DUP-01')

        return None

    def test_same_code_different_warehouse(self, warehouse_factory, location_factory) -> None:
        wh1 = warehouse_factory()
        wh2 = warehouse_factory()
        loc1 = location_factory(warehouse=wh1, code='SHARED-01')
        loc2 = location_factory(warehouse=wh2, code='SHARED-01')
        assert loc1.pk != loc2.pk

        return None
```

- Por cada `UniqueConstraint` o campo `unique=True`: un test que intenta crear el duplicado y espera `ValidationError`.
- Cuando la unicidad es compuesta (ej. `unique_together` en múltiples campos), incluir también un test que confirma que **sí** se puede crear el mismo valor en otra dimensión (ej. mismo código en distinta bodega).

---

### TestProperties

Cubre **cualquier tipo de property** definida en el modelo:

| Tipo | Cómo testear |
|---|---|
| `@queryable_property(annotation_based=True)` | Consultar con `select_properties(...)` para obtener el valor anotado |
| `@property` de Python | Acceder directamente en la instancia: `instance.mi_property` |
| `@cached_property` | Igual que `@property`; verificar que el valor es correcto en el acceso |

```python
class TestProperties:
    # queryable_property — requiere select_properties()
    def test_total_products(self, income_factory, income_product_factory) -> None:
        income = income_factory()
        income_product_factory(income=income, quantity=5)
        income_product_factory(income=income, quantity=3)

        result = Income.objects.select_properties('total_products').get(pk=income.pk)
        assert result.total_products == 8

        return None

    def test_total_products_empty(self, income_factory) -> None:
        income = income_factory()
        result = Income.objects.select_properties('total_products').get(pk=income.pk)
        assert result.total_products == 0

        return None

    def test_has_document_invoice_true(self, income_factory) -> None:
        income = income_factory(invoice_file='income/invoice_files/test.pdf')
        result = Income.objects.select_properties('has_document_invoice').get(pk=income.pk)
        assert result.has_document_invoice is True

        return None

    def test_has_document_invoice_false(self, income_factory) -> None:
        income = income_factory(invoice_file=None)
        result = Income.objects.select_properties('has_document_invoice').get(pk=income.pk)
        assert result.has_document_invoice is False

        return None

    # @property de Python — acceso directo en la instancia
    def test_full_name(self, company_factory) -> None:
        instance = company_factory(dni='12345678-9', business_name='Acme')
        assert instance.full_name == '12345678-9 - Acme'

        return None
```

- Testear tanto el caso base (valor esperado) como el caso vacío/borde (ej. 0 cuando no hay hijos, `False` cuando el campo es vacío).
- Las `@queryable_property` **siempre** via `select_properties()` — acceso directo a la instancia no ejecuta la anotación ORM.

---

### TestMethods

```python
class TestMethods:
    def test_set_request_status_completed(
        self, income_factory, request_factory_obj, request_product_factory, income_product_factory
    ) -> None:
        request = request_factory_obj()
        product = request_product_factory(request=request, quantity=10).product
        income = income_factory(request=request)
        income_product_factory(income=income, product=product, quantity=10)

        income.set_request_status()

        request.refresh_from_db()
        assert request.status == 'CO'

        return None

    def test_set_request_status_partial(
        self, income_factory, request_factory_obj, request_product_factory, income_product_factory
    ) -> None:
        request = request_factory_obj()
        product = request_product_factory(request=request, quantity=10).product
        income = income_factory(request=request)
        income_product_factory(income=income, product=product, quantity=5)

        income.set_request_status()

        request.refresh_from_db()
        assert request.status == 'PC'

        return None

    def test_set_request_status_no_request(self, income_factory) -> None:
        income = income_factory(request=None)
        income.set_request_status()   # no debe lanzar excepción

        return None
```

- `TestMethods` cubre **cualquier método** del modelo: `__str__`, métodos de negocio, helpers internos.
- Un test por rama lógica relevante: caso feliz, caso parcial, caso vacío/sin FK opcional.
- Usar `refresh_from_db()` para verificar efectos en la base de datos.
- Los métodos que retornan `None` y producen efectos secundarios se verifican por sus efectos, no por su valor de retorno.
- Para `__str__`, nombrar el test describiendo el formato: `test_str_returns_<descripción>`.

```python
# __str__ va en TestMethods
def test_str_returns_number_and_invoice(self, income_factory) -> None:
    instance = income_factory(number='INC-001', invoice_number='FAC-999')
    assert str(instance) == 'INC-001 - FAC-999'

    return None
```

---

### TestSignals

```python
class TestSignals:
    def test_reverse_income_signal_fires_on_save(self, income_factory) -> None:
        from unittest.mock import patch

        with patch('inventory.signals.income.reverse_income') as mock_signal:
            income = income_factory()
            income.save()
            assert mock_signal.called

        return None
```

- Cubrir que el signal registrado en `Meta.signals` se dispara ante el evento correcto.
- Si el callback tiene lógica de negocio observable (ej. crea registros en otra tabla), preferir testear el efecto en lugar de mockear.

---

### TestQuerySets

Cubre cada método público del QuerySet custom del modelo. El objetivo es verificar que cada método filtra **exactamente** los tipos correctos y excluye los demás — no testear la lógica de negocio (eso va en `TestUseCases`).

```python
class TestQuerySets:
    def test_only_sum_filtra_ingresos(
        self, product_factory, location_factory, product_stock_factory
    ) -> None:
        product = product_factory()
        location = location_factory()
        ingreso = product_stock_factory(product=product, location=location, type='Ingreso', quantity=10)
        qs = ProductStock.objects.filter(product=product).only_sum()
        assert qs.count() == 1
        assert qs.first().pk == ingreso.pk

        return None

    def test_only_sum_excluye_egresos_y_reservas(
        self, product_factory, location_factory, product_stock_factory
    ) -> None:
        product = product_factory()
        location = location_factory()
        product_stock_factory(product=product, location=location, type='Ingreso', quantity=10)
        product_stock_factory(product=product, location=None, type='Reserva por Venta', quantity=4)
        qs = ProductStock.objects.filter(product=product).only_sum()
        assert qs.count() == 1
        assert qs.first().type == 'Ingreso'

        return None
```

Reglas:
- Un test por método: verifica que devuelve el tipo correcto.
- Un test adicional por método que confirma que **excluye** tipos relacionados pero distintos (ej. `only_sum` no devuelve `Reserva por Venta`).
- Usar el mismo `product` y `location` dentro de cada test para aislar el conteo.
- Crear los datos en el orden correcto según las reglas de negocio (ej. crear una reserva `RES_SUM_TYPE` antes que su liberación `RES_SUB_TYPE` si hay validaciones de signal).
- Los tipos de `RES_SUM_TYPE`/`RES_SUB_TYPE` siempre se crean con `location=None` — `ProductStock.location` es nulo únicamente para movimientos de reserva (ver `docs/00-proyecto-gms.md` § ProductStock).

---

### TestUseCases

Cubre escenarios de negocio completos que combinan múltiples operaciones. La diferencia con `TestSignals` es el foco: `TestSignals` prueba un signal a la vez; `TestUseCases` prueba secuencias de acciones y su efecto acumulado sobre el estado del sistema.

```python
class TestUseCases:
    def test_flujo_completo_ingreso_reserva_egreso_liberacion(
        self, product_factory, location_factory, product_stock_factory
    ) -> None:
        product = product_factory()
        location = location_factory()

        product_stock_factory(product=product, location=location, type='Ingreso', quantity=20)
        product.refresh_from_db()
        assert product.stock_physical == 20
        assert product.stock_busy == 0
        assert product.stock == 20

        product_stock_factory(product=product, location=None, type='Reserva por Venta', quantity=8)
        product.refresh_from_db()
        assert product.stock_physical == 20
        assert product.stock_busy == 8
        assert product.stock == 12

        product_stock_factory(product=product, location=location, type='Egreso Manual', quantity=10)
        product.refresh_from_db()
        assert product.stock_physical == 10
        assert product.stock_busy == 8
        assert product.stock == 2

        product_stock_factory(product=product, location=None, type='Reserva Liberada por Cancelación', quantity=3)
        product.refresh_from_db()
        assert product.stock_physical == 10
        assert product.stock_busy == 5
        assert product.stock == 5

        return None
```

Reglas:
- Cada test cubre un **escenario**, no una operación aislada.
- Verificar el estado del sistema (`refresh_from_db()`) después de cada paso relevante cuando el test quiere confirmar el estado intermedio.
- Incluir siempre: el caso feliz completo, casos límite (reservar exactamente el disponible, egresar exactamente el disponible) y casos de múltiples ubicaciones cuando la lógica es por ubicación.
- Los tests de `TestUseCases` pueden ser más largos que los de otras inner classes — está permitido si el escenario lo requiere.
- Nombrar los tests describiendo el escenario de negocio, no la mecánica técnica: `test_flujo_completo_ingreso_reserva_egreso_liberacion`, no `test_multiple_signals_execute_correctly`.

---

## Tests de serializers (`<app>/tests/serializers/<modelo>.py`)

### Estructura general

```python
import pytest
from inventory.serializers.v1.product import ProductStockHistoryDownloadSerializer


@pytest.mark.django_db
class TestProductStockHistoryDownloadSerializer:

    class TestValidate: ...
    class TestGetters: ...
    class TestCreate: ...
```

### Inner classes y cuándo usarlas

| Inner class | Cuándo incluirla | Qué testea |
|---|---|---|
| `TestValidate` | Si el serializer define `validate()` o `validate_<field>()` | Que la validación rechaza datos inválidos y acepta válidos |
| `TestGetters` | Si hay `SerializerMethodField` con lógica | Que cada `get_<field>()` retorna el valor/tipo esperado |
| `TestCreate` | Si el serializer define `create()` con lógica custom alcanzable vía payload | Que `serializer.save()` produce el objeto con los efectos esperados |
| `TestUpdate` | Si el serializer define `update()` con lógica custom | Que `serializer.save(instance=...)` aplica los cambios correctamente |
| `TestFields` | Si hay lógica de inclusión/exclusión de campos (`DynamicFieldsMixin`) | Que los campos se filtran correctamente según permisos o parámetros |

### Piso mínimo: `test_serialization`

Todo serializer debe tener al menos un `test_serialization` que verifica valores concretos — `pk`, `id_as_code` y al menos un campo de negocio propio — no solo `isinstance(data, dict)`. Un único test cubre el shape completo incluyendo relaciones anidadas; no crear métodos separados por campo o tipo de relación.

```python
@pytest.mark.django_db
class TestProductSerializer:
    def test_serialization(self, request_factory, product_factory) -> None:
        instance = product_factory()
        serializer = ProductSerializer(
            instance=instance, context={"request": request_factory.get()}
        )
        data = serializer.data

        assert data["pk"] == str(instance.pk)
        assert data["id_as_code"] == instance.id_as_code
        assert data["name"] == instance.name
        assert data["category"]["pk"] == str(instance.category.pk)  # relación anidada

        return None
```

---

### TestValidate

```python
class TestValidate:
    def test_valid_date_range(self, request_factory, product_factory) -> None:
        data = {
            'product': str(product_factory().pk),
            'started_at': '2024-01-01',
            'ends_at': '2024-01-31',
        }
        serializer = ProductStockHistoryDownloadSerializer(
            data=data,
            context={'request': request_factory},
        )
        assert serializer.is_valid(), serializer.errors

        return None

    def test_equal_dates_raises_error(self, request_factory) -> None:
        data = {
            'started_at': '2024-01-01',
            'ends_at': '2024-01-01',
        }
        serializer = ProductStockHistoryDownloadSerializer(
            data=data,
            context={'request': request_factory},
        )
        assert not serializer.is_valid()
        assert 'started_at' in serializer.errors

        return None

    def test_start_after_end_raises_error(self, request_factory) -> None:
        data = {
            'started_at': '2024-02-01',
            'ends_at': '2024-01-01',
        }
        serializer = ProductStockHistoryDownloadSerializer(
            data=data,
            context={'request': request_factory},
        )
        assert not serializer.is_valid()
        assert 'started_at' in serializer.errors

        return None
```

- Un test por rama del `validate()`: caso válido, cada caso de error.
- Verificar que el campo correcto aparece en `serializer.errors`.
- Pasar siempre `context={'request': request_factory}` si el serializer lo requiere.

---

### TestGetters

```python
class TestGetters:
    def test_get_file_name_with_product(self, request_factory, product_factory) -> None:
        product = product_factory()
        instance = {'product': product}
        serializer = ProductStockHistoryDownloadSerializer(
            instance=instance,
            context={'request': request_factory},
        )
        name = serializer.data['file_name']
        assert name.endswith('.xlsx')
        assert product.full_code.lower().replace(' ', '_') in name

        return None

    def test_get_file_name_with_date_range(self, request_factory) -> None:
        instance = {'started_at': '2024-01-01', 'ends_at': '2024-01-31'}
        serializer = ProductStockHistoryDownloadSerializer(
            instance=instance,
            context={'request': request_factory},
        )
        name = serializer.data['file_name']
        assert 'historial' in name
        assert name.endswith('.xlsx')

        return None

    def test_get_product_stock_history_file_returns_bytes(
        self, request_factory, product_factory, product_stock_factory
    ) -> None:
        import io

        product = product_factory()
        product_stock_factory(product=product)
        instance = {'product': product}
        serializer = ProductStockHistoryDownloadSerializer(
            instance=instance,
            context={'request': request_factory},
        )
        result = serializer.data['product_stock_history_file']
        assert isinstance(result, io.BytesIO)

        return None
```

- Un test por variante del `SerializerMethodField`: cada rama del `if` en el getter merece su propio test.
- Para getters que generan archivos, verificar el tipo del retorno (`BytesIO`, `str`, etc.) y propiedades clave, no el contenido exacto del archivo.

---

### TestCreate

```python
class TestCreate:
    def test_create_returns_validated_data(self, request_factory, product_factory) -> None:
        product = product_factory()
        data = {
            'product': str(product.pk),
            'started_at': '2024-01-01',
            'ends_at': '2024-01-31',
        }
        serializer = ProductStockHistoryDownloadSerializer(
            data=data,
            context={'request': request_factory},
        )
        assert serializer.is_valid(), serializer.errors
        result = serializer.save()
        assert isinstance(result, dict)

        return None
```

---

---

## Tests de services (`<app>/tests/services/<servicio>.py`)

Los services se testean en `tests/services/<nombre_servicio>.py`. No van en `tests/models/` aunque el service trabaje sobre un modelo — los tests del service verifican **orquestación y efectos externos**, no el estado del modelo.

### Estructura base

```python
# inventory/tests/services/stock_movement.py
import pytest
from unittest.mock import patch

from inventory.services.stock_movement import StockMovementService


@pytest.mark.django_db
class TestStockMovementService:
    class TestCreate:
        def test_creates_movement_and_returns_instance(
            self, product_factory, location_factory
        ) -> None:
            product = product_factory()
            location = location_factory()
            service = StockMovementService(product=product, location=location)

            result = service.create(type_="Ingreso", quantity=10)

            assert result.pk is not None
            assert result.quantity == 10
            assert result.type == "Ingreso"

            return None

        def test_invalid_quantity_raises_error(
            self, product_factory, location_factory
        ) -> None:
            product = product_factory()
            location = location_factory()
            service = StockMovementService(product=product, location=location)

            with pytest.raises(ValueError, match="positiva"):
                service.create(type_="Ingreso", quantity=0)

            return None
```

### Inner classes y cuándo incluirlas

| Inner class | Cuándo | Qué testea |
|---|---|---|
| `Test<MetodoPrincipal>` | Un método público del service | Ramas lógicas: caso feliz, caso vacío, errores de validación |
| `Test<NombreEspecifico>` | Cuando el service tiene varios métodos públicos independientes | Un inner class por método |

Para services con un único método público (`run`, `execute`), la clase raíz puede contener los tests directamente sin inner classes.

### Servicio funcional (no clase)

Cuando el service expone una función en lugar de una clase, la clase raíz se nombra `Test<NombreDeLaFuncion>`:

```python
@pytest.mark.django_db
class TestFinalizeCart:
    def test_creates_sale_from_cart(self, cart_factory) -> None:
        from sale.services.finalize import finalize_cart

        cart = cart_factory()
        sale = finalize_cart(cart)

        assert sale.cart == cart
        assert sale.pk is not None

        return None
```

### Mock de APIs externas en services

Preferir mockear al nivel más cercano a la llamada externa:

```python
# ✅ Mockear el método del servicio que llama a la API externa
with patch.object(external_service, "send_request", return_value={"status": "ok"}):
    ...

# ✅ Mockear el service completo cuando se testea su caller
with patch("inventory.services.stock_movement.StockMovementService") as mock_svc:
    mock_svc.return_value.create.return_value = movement_instance
    caller_function()

# ❌ No mockear el cliente HTTP subyacente si hay un mock de nivel más alto disponible
with patch("requests.post", ...):  # demasiado bajo
    ...
```

### `conftest.py` de services

Usar `conftest.py` en `tests/services/` para mocks de sesión propios del service (conexiones externas, drivers, etc.):

```python
# miapp/tests/services/conftest.py
@pytest.fixture(scope="session", autouse=True)
def _mock_external_api():
    """Prevent any real API calls during the test session."""
    with patch("miapp.services.external_client.send") as mock:
        mock.return_value = {"ok": True}
        yield mock
```

---

## Tests de viewsets (`<app>/tests/viewsets/<modelo>.py`)

### Estructura del archivo

Cada archivo `tests/viewsets/<modelo>.py` tiene dos zonas:

```
1. View bindings     — module-level, una variable por acción
2. TestXxxViewSet    — @pytest.mark.django_db, inner classes por acción HTTP
```

No hay helper functions — los fixtures globales `request_factory` y `render` cubren esa necesidad.

### View bindings

Una variable por acción del ViewSet, al nivel del módulo:

```python
from inventory.viewsets.v1 import ProductViewSet

_LIST_VIEW     = ProductViewSet.as_view({"get": "list"})
_RETRIEVE_VIEW = ProductViewSet.as_view({"get": "retrieve"})
_CREATE_VIEW   = ProductViewSet.as_view({"post": "create"})
_PATCH_VIEW    = ProductViewSet.as_view({"patch": "partial_update"})
_DESTROY_VIEW  = ProductViewSet.as_view({"delete": "destroy"})
_EXPORT_VIEW   = ProductViewSet.as_view({"get": "export"})   # @action
```

No abstraer los view bindings — la variación (ViewSet + acción) es exactamente la información útil.

### Estructura de clases

```python
@pytest.mark.django_db           # solo en la clase raíz
class TestProductViewSet:
    class TestList:              # GET /
    class TestRetrieve:          # GET /{pk}/
    class TestCreate:            # POST /
    class TestPartialUpdate:     # PATCH /{pk}/
    class TestDestroy:           # DELETE /{pk}/
    class TestActions:           # todos los @action agrupados aquí
        class TestExport:        #   una sub-clase por @action
        class TestMetrics:
```

### Patrón canónico completo

```python
import pytest

from inventory.viewsets.v1 import ProductViewSet

_LIST_VIEW   = ProductViewSet.as_view({"get": "list"})
_CREATE_VIEW = ProductViewSet.as_view({"post": "create"})
_PATCH_VIEW  = ProductViewSet.as_view({"patch": "partial_update"})


@pytest.mark.django_db
class TestProductViewSet:
    class TestList:
        def test_returns_200(self, request_factory, product_factory) -> None:
            product_factory()
            response = _LIST_VIEW(request_factory.get())
            assert response.status_code == 200
            return None

        def test_unauthenticated_returns_401(self, request_factory) -> None:
            response = _LIST_VIEW(request_factory.get(auth_user=None))
            assert response.status_code == 401
            return None

    class TestCreate:
        def test_creates_instance(self, request_factory, category_factory) -> None:
            category = category_factory()
            response = _CREATE_VIEW(
                request_factory.post({"name": "Nuevo Producto", "category": str(category.pk)})
            )
            assert response.status_code == 201
            return None

        def test_name_required(self, request_factory) -> None:
            response = _CREATE_VIEW(request_factory.post({}))
            assert response.status_code == 400
            assert "name" in response.data
            return None

    class TestPartialUpdate:
        def test_patch_persists_in_db(
            self, request_factory, product_factory
        ) -> None:
            instance = product_factory(name="Viejo")
            response = _PATCH_VIEW(
                request_factory.patch({"name": "Nuevo"}), pk=str(instance.pk)
            )
            assert response.status_code == 200
            instance.refresh_from_db()
            assert instance.name == "Nuevo"
            return None

    class TestActions:
        class TestExport:
            def test_returns_xlsx(
                self, render, request_factory, product_factory
            ) -> None:
                product_factory()
                response = render(_EXPORT_VIEW(request_factory.get()))
                assert response.status_code == 200
                assert "spreadsheetml" in response["Content-Type"]
                return None
```

### Cuándo usar `user` vs `request_factory`

| Necesidad | Fixture |
|---|---|
| Solo autenticar el request | `request_factory` — no necesitas `user` directamente |
| Referenciar el usuario para linkear FKs | `user` directamente |
| Ambas cosas | `user` + `request_factory` (comparten el mismo usuario base) |

```python
# ✅ Solo autenticación
def test_list(self, request_factory) -> None:
    response = _LIST_VIEW(request_factory.get())
    ...

# ✅ Necesitas user para FK
def test_filtered_by_user(self, request_factory, user, cart_factory) -> None:
    cart = cart_factory(company=user.company)
    response = _LIST_VIEW(request_factory.get())
    ...
```

---

## Uso de `freezegun` para tests temporales

Para tests que dependen de la fecha actual (validaciones con `timezone.now()`):

```python
from freezegun import freeze_time


@freeze_time("2025-06-15")
def test_sale_is_expired(self, sale_factory) -> None:
    instance = sale_factory(deadline="2025-06-14")
    assert instance.is_expired is True
    return None
```

---

## Mock de APIs externas en `conftest.py`

Cuando la app usa servicios externos (Google Maps, APIs de pago, etc.), las llamadas deben bloquearse en tests con fixtures `autouse`. El patrón es usar `unittest.mock.patch` como fixture de sesión en el `conftest.py` de la app:

```python
# miapp/tests/conftest.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(scope="session", autouse=True)
def mock_google_maps_api(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        with patch(
            "main.utils.google_maps.get_coordinates",
            return_value={"lat": -33.4569, "lng": -70.6483},
        ):
            yield
```

**Reglas:**
- Usar `scope="session"` para que el mock sea válido durante toda la sesión de tests.
- Pasar siempre `django_db_setup` y `django_db_blocker` como dependencias para evitar conflictos con el acceso a la DB.
- Mockear al nivel más bajo posible (método del modelo, no el cliente HTTP) para no interferir con la lógica de negocio.
- Declarar todos los mocks de APIs externas en el `conftest.py` de la app que los usa, no en el `conftest.py` raíz.

---

## Convenciones generales

- Todos los métodos de test retornan `None` explícitamente (`return None`).
- Usar siempre `instance.refresh_from_db()` tras un PATCH/save para verificar el estado persistido.
- En tests de constraints del modelo, usar `pytest.raises(ValidationError)` de `django.core.exceptions`.
- En tests de viewsets, verificar `response.status_code` y `response.data` para errores de validación.
- Los `assert` sobre errores van **dentro** del bloque `with pytest.raises(...)`.
- No usar `setUp`/`tearDown`; usar fixtures de pytest.
- No crear datos en `conftest.py`; crear datos dentro de cada test con factories.
- No usar `isinstance(data, dict)` como único assert en `test_serialization` — verificar valores concretos.

---

## Ejecutar tests

```bash
# Todos los tests
pytest

# En paralelo (recomendado)
pytest -n 6

# Tests de una app
pytest organization/tests/ -v

# Con cobertura
pytest --cov=organization

# Dentro del contenedor Docker
docker-compose -f docker-compose.dev.yml exec app-django-gms-dev bash
pytest <app>/tests/ -v
```

# 17 — Estilo Python: Linter y Formato

---

## Linter: ruff

El proyecto usa **ruff** como linter y formatter. Configuración en `pyproject.toml`.

### Reglas activas

| Código | Descripción |
|---|---|
| `E` | pycodestyle errors |
| `F` | Pyflakes (imports no usados, variables no definidas, etc.) |
| `I` | isort — orden de imports |
| `B` | flake8-bugbear — errores comunes y malas prácticas |

### Configuración destacada

```toml
[tool.ruff]
line-length = 120
exclude = ["**/migrations/*.py"]

[tool.ruff.lint]
select = ["E", "F", "I", "B"]
ignore = []

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]        # re-exportaciones permitidas
"**/factories/*.py" = ["F811"]  # redefinición de nombre permitida
```

### Verificación

```bash
ruff check .          # revisar errores
ruff check --fix .    # corregir lo que sea auto-fixable
```

Siempre ejecutar `ruff check .` antes de entregar código. **No dejar errores sin corregir.**

---

## Orden de imports (isort vía ruff)

Los imports se organizan en tres bloques separados por una línea en blanco, en este orden:

```python
# 1. Stdlib
import os
import re
from pathlib import Path

# 2. Third-party
from django.db import models
from rest_framework import serializers

# 3. Local (proyecto)
from inventory.models import Product
from main.utils.views.permission import PermissionRequiredMixin
```

---

## Reglas de Legibilidad y Formato

Estas reglas **no** las impone ruff — se aplican a todo código nuevo o modificado.

---

### Regla 0 — Docstrings: solo cuando el WHY no es obvio

Los docstrings son opcionales. Agregar uno **solo cuando** la intención o el motivo no es evidente por el nombre del método o sus parámetros: comportamiento no obvio, restricción oculta, workaround, o lógica que sorprendería a un lector.

```python
# ✗ — el nombre ya lo explica todo, docstring redundante
def get_initial_queryset(self, request=None):
    """Retorna el queryset inicial."""
    ...

# ✓ — el WHY no es evidente desde el nombre
def optimize_queryset(self, qs):
    """Desactiva la optimización automática de la librería para evitar FieldError con FKs virtuales."""
    return qs
```

Para cuando la explicación necesita más contexto:

```python
def _paginate_items(items, first_page_limit, page_limit):
    """
    Divide ítems en páginas diferenciando la primera (que tiene bloque de info)
    de las siguientes. Retorna al menos una página vacía si items está vacío.
    """
    ...
```

---

### Regla 1 — Línea en blanco ANTES de bloques de control y `return`

Dejar siempre una línea en blanco antes de `if`, `for`, `while`, `try`, `with` y `return`,
**salvo que**:

- Sea la primera instrucción del cuerpo de la función/método (inmediatamente después de `def ...:`
  o del docstring de apertura).
- La línea anterior ya termine en `:` — es decir, sea apertura de bloque
  (`else:`, `elif ...:`, `try:`, `except ...:`, `with ...:`, etc.).
- Ya haya una línea en blanco antes.
- La línea anterior sea un decorador (`@algo`).
- Esté dentro de una comprehension o expresión entre brackets (`[...]`, `(...)`, `{...}`).

**No** se añade blank antes de `elif`, `else`, `except` ni `finally` — son continuaciones del
bloque anterior y deben permanecer visualmente adheridas a él.

---

### Regla 2 — Línea en blanco DESPUÉS del fin de un bloque

Cuando el código dentro de un bloque termina y el siguiente código vuelve a un nivel de
indentación menor, debe haber una línea en blanco entre ellos,
**salvo que** la siguiente línea sea `elif`, `else`, `except` o `finally`
(continuaciones del mismo bloque).

---

### Ejemplo canónico completo

```python
# ✓ Correcto
def save_client(self, request):
    """
    Guarda la información del cliente asociado al carrito activo.
    """
    cart = Cart.objects.filter(is_active=True).first()

    if not cart:
        return Response({'detail': 'No hay carrito activo.'}, status=status.HTTP_400_BAD_REQUEST)

    client_pk = request.data.get('client_pk', '').strip()

    if client_pk:
        try:
            client = SaleClient.objects.get(pk=client_pk)
        except SaleClient.DoesNotExist:
            return Response({'detail': 'Cliente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        cart.sale_client = client
    else:
        cart.sale_client = None

    cart.sale_client_address = None
    cart.save(update_fields=['sale_client', 'sale_client_address'])

    try:
        cart.cart_address.delete()
    except CartAddress.DoesNotExist:
        pass

    return Response({'success': True})
```

---

### Tabla de excepciones

| Situación | ¿Blank? | Motivo |
|---|---|---|
| `if` como primera instrucción de función | No | Sigue directamente al `def ...:` |
| `else:` / `elif:` / `except:` / `finally:` | No antes | Son continuación del bloque anterior |
| `return` como única instrucción de un bloque `if` | Depende | Si es la primera línea del bloque (prev termina en `:`): no |
| `for` dentro de `[x for x in ...]` | No | Está dentro de brackets (comprehension) |
| Línea en blanco ya existente antes del `if` | No añadir otra | Ya cumple la regla |

---

## Pre-commit

El proyecto tiene `.pre-commit-config.yaml` con `ruff-check` (con `--fix`) y `ruff-format`.
El formatter aplica el estilo de Black (longitud 120, comillas, trailing commas).
Las reglas de blancos lógicos (Regla 1 y 2) y los docstrings **no** los aplica el formatter
— son responsabilidad del desarrollador (o de Claude al escribir código).

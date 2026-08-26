"""
Parche de compatibilidad entre `model_utils.FieldTracker` y PKs generadas en Python
(`uuid7`, ver `BaseV2`/`BaseV3`).

`FieldInstanceTracker.set_saved_fields()` usa `not instance.pk` para decidir si una
instancia es "nueva" (sin estado previo conocido, `saved_data = {}`) o si ya tiene un
estado guardado que capturar (`saved_data = self.current()`). Esa heurística asume que un
PK truthy implica que la fila existe (fue cargada desde la base o ya se guardó). Con PKs
enteras autoincrementales (`BaseModel`) eso es cierto: `pk` es `None` hasta el `INSERT`.

Con `uuid7` como `default` del campo PK (`BaseV2`/`BaseV3`), el PK ya tiene un valor válido
al construir la instancia en Python, ANTES de cualquier guardado — `set_saved_fields()` cree
erróneamente que esos valores recién construidos son el estado "guardado", rompiendo
cualquier lógica que dependa de `tracker.previous(field)`/`tracker.has_changed(field)` para
distinguir creación de actualización (ver `CheckFlowStatusConstraint`, que usa exactamente
eso para permitir que una `post_save` de creación cambie un campo controlado por flujo sin
disparar una validación de transición inválida).

Se parchea a `instance._state.adding`, que sí distingue correctamente "nunca guardada" —
con una salvedad: `Model.from_db()` (el método que usa CUALQUIER carga de QuerySet) llama a
`cls(*values)` ANTES de corregir `_state.adding = False` en la instancia resultante. En ese
instante (dentro de `__init__`, que es donde `FieldTracker` inicializa el tracker de cada
instancia) `_state.adding` sigue en `True` (el valor por defecto). Sin compensar esto,
CUALQUIER objeto cargado desde la base perdería su snapshot del tracker — `saved_data`
quedaría vacío, y `has_changed()` reportaría `True` para todos los campos de cualquier
instancia recién cargada, sin haber cambiado nada.

Se compensa reinyectando `Model.from_db` (una única vez, a nivel de `django.db.models.Model`
— lo heredan todos los modelos del proyecto, no hace falta tocar cada metaclase) para volver
a llamar `tracker.set_saved_fields()` justo después de que Django corrija `_state.adding`.

Importado desde `django_general_utils/models/__init__.py`, se ejecuta una sola vez al
importar el paquete — antes de que cualquier modelo del proyecto ejecute una query real.
"""
from django.db.models import Model as DjangoModel
from model_utils.tracker import FieldInstanceTracker, lightweight_deepcopy


def _set_saved_fields(self, fields=None):
    if self.instance._state.adding:
        self.saved_data = {}
    elif fields is None:
        self.saved_data = self.current()
    else:
        self.saved_data.update(**self.current(fields=fields))

    for field, field_value in self.saved_data.items():
        self.saved_data[field] = lightweight_deepcopy(field_value)


FieldInstanceTracker.set_saved_fields = _set_saved_fields

_original_from_db = DjangoModel.from_db.__func__


@classmethod
def _from_db_with_tracker_resync(cls, db, field_names, values):
    instance = _original_from_db(cls, db, field_names, values)
    tracker = getattr(instance, 'tracker', None)

    if tracker is not None:
        tracker.set_saved_fields()

    return instance


DjangoModel.from_db = _from_db_with_tracker_resync

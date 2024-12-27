import numpy as np

from pgvector.django import VectorField as PGVectorField


class VectorField(PGVectorField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value

        if isinstance(value, np.ndarray):
            return value.tolist()

        return [float(v) for v in value[1:-1].split(',')]

    def to_python(self, value):
        if value is None:
            return value

        if isinstance(value, list):
            return value

        if isinstance(value, np.ndarray):
            return value.tolist()

        return [float(v) for v in value[1:-1].split(',')]

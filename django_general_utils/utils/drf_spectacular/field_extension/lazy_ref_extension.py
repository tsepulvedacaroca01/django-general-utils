from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import Direction

from ....utils.drf.fields import LazyRefSerializerField


class LazyRefSerializerFieldExtension(OpenApiSerializerFieldExtension):
    # Ensure annotations use different read/write serializers when using LazyRefSerializer
    target_class = LazyRefSerializerField
    match_subclasses = True

    def map_serializer_field(self, auto_schema, direction: Direction):
        component = auto_schema.resolve_serializer(self.target.get_serializer(), direction, True)

        return component.ref if component else None

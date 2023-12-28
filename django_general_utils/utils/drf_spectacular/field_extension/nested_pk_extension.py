from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import Direction

from ....utils.drf.fields import NestedPrimaryKeyRelatedField


class NestedPkExtension(OpenApiSerializerFieldExtension):
    # Ensure annotations use different read/write serializers when using NestedPrimaryKeyRelatedField
    target_class = NestedPrimaryKeyRelatedField
    match_subclasses = True

    def map_serializer_field(self, auto_schema, direction: Direction):
        if direction == "response":
            # target is NestedPrimaryKeyRelatedField instance.
            # build a component from the serializer and return a reference to that component
            component = auto_schema.resolve_serializer(self.target.get_serializer(), direction, True)
            
            return component.ref if component else None
        else:
            # Return a primary key schema
            return build_basic_type(OpenApiTypes.INT)  # or whatever key you use

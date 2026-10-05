class CachedChildSerializerMixin:
    """
    Builds the nested serializer of a relation field ONCE per bound field instead of once per
    serialized object.

    ``NestedPrimaryKeyRelatedField`` and ``LazyRefSerializerField`` used to instantiate a brand-new
    serializer for every object they render. DRF deep-copies the declared fields and
    ``ModelSerializer.get_fields`` walks the model on each new instance, so that dominated the CPU of a
    list endpoint (~40-60 % of a list of 25 carts, measured with cProfile).

    A bound field instance lives as long as its parent serializer instance (``ListSerializer`` binds one
    ``child`` and reuses it for every row), and everything that determines the nested serializer is
    fixed for that lifetime: ``serializer_class``, ``extra_kwargs``, the root ``context`` and the
    ``parsed_query`` the parent computed for this field. The cache is keyed on the identities of the
    parent and of the context, so a re-bound field or a replaced context builds a fresh serializer.

    ``get_serializer`` is untouched (it still returns a new serializer each call, as the write path and
    subclasses expect); only the read path (``to_representation``) goes through ``get_cached_serializer``.
    The cached serializer is built WITHOUT ``instance`` and used through ``to_representation`` — the
    ``.data`` property would memoize the first object's representation on it.
    """

    def get_cached_serializer(self):
        parent = self.parent
        context = self.context
        cached = self.__dict__.get('_child_serializer_cache')

        if cached is not None and cached[0] is parent and cached[1] is context:
            return cached[2]

        serializer = self.get_serializer()
        self._child_serializer_cache = (parent, context, serializer)

        return serializer

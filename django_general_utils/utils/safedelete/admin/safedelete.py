from collections import OrderedDict

from django.db.models import F
from safedelete.admin import SafeDeleteAdmin as BaseSafeDeleteAdmin
from safedelete.config import FIELD_NAME


class SafeDeleteAdmin(BaseSafeDeleteAdmin):
    with_deleted_objects = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'is_deleted' in self.list_display:
            def is_deleted(obj):
                return obj.is_active

            is_deleted.boolean = True
            setattr(self, 'is_deleted', is_deleted)

        if 'is_stopped' in self.list_display:
            def is_stopped(obj):
                return obj.is_stopped

            is_stopped.boolean = True
            setattr(self, 'is_stopped', is_stopped)

    def get_queryset(self, request):
        try:
            if self.with_deleted_objects or FIELD_NAME in request.GET:
                queryset = self.model.all_objects.all()
            else:
                queryset = self.model.filter.all()
        except Exception:
            queryset = self.model._default_manager.all()

        if self.field_to_highlight:
            queryset = queryset.annotate(_highlighted_field=F(self.field_to_highlight))

        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)

        return queryset

    def get_form(self, request, obj=None, **kwargs):
        form = super(SafeDeleteAdmin, self).get_form(request, obj, **kwargs)

        form.base_fields = OrderedDict(form.base_fields)

        form.base_fields.move_to_end('is_active')
        form.base_fields.move_to_end('stopped_at')

        return form

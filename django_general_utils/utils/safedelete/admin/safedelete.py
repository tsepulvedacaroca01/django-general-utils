from collections import OrderedDict

from django.contrib.admin import helpers
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.utils import (
    flatten_fieldsets,
    unquote,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.core.exceptions import ValidationError
from django.db.models import F
from django.forms.formsets import all_valid
from django.utils.translation import gettext as _
from safedelete.admin import FIELD_NAME
from safedelete.admin import SafeDeleteAdmin as BaseSafeDeleteAdmin
from simple_history.admin import SimpleHistoryAdmin

IS_POPUP_VAR = "_popup"
TO_FIELD_VAR = "_to_field"

HORIZONTAL, VERTICAL = 1, 2


class SafeDeleteAdmin(BaseSafeDeleteAdmin, SimpleHistoryAdmin):
    with_deleted_objects = False
    history_list_display = ['status']

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
            with_deleted_objects = (
                    self.with_deleted_objects or
                    FIELD_NAME in request.GET or
                    'change' in request.path or
                    'create' in request.path
            )
            if with_deleted_objects:
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


    def _changeform_view(self, request, object_id, form_url, extra_context):
        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField(
                "The field %s cannot be referenced." % to_field
            )

        if request.method == "POST" and "_saveasnew" in request.POST:
            object_id = None

        add = object_id is None

        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id), to_field)

            if request.method == "POST":
                if not self.has_change_permission(request, obj):
                    raise PermissionDenied
            else:
                if not self.has_view_or_change_permission(request, obj):
                    raise PermissionDenied

            if obj is None:
                return self._get_obj_does_not_exist_redirect(
                    request, self.opts, object_id
                )

        fieldsets = self.get_fieldsets(request, obj)
        ModelForm = self.get_form(
            request, obj, change=not add, fields=flatten_fieldsets(fieldsets)
        )
        if request.method == "POST":
            form = ModelForm(request.POST, request.FILES, instance=obj)
            formsets, inline_instances = self._create_formsets(
                request,
                form.instance,
                change=not add,
            )

            form_validated = form.is_valid()

            if form_validated:
                new_object = self.save_form(request, form, change=not add)
            else:
                new_object = form.instance
            if all_valid(formsets) and form_validated:
                try:
                    self.save_model(request, new_object, form, not add)
                except ValidationError as e:
                    form_validated = False

                    for _field, _error in e.error_dict.items():
                        form.add_error(_field, _error)

                if form_validated:
                    self.save_related(request, form, formsets, not add)

                    change_message = self.construct_change_message(
                        request, form, formsets, add
                    )
                    if add:
                        self.log_addition(request, new_object, change_message)
                        return self.response_add(request, new_object)
                    else:
                        self.log_change(request, new_object, change_message)
                    return self.response_change(request, new_object)
            else:
                form_validated = False
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(
                    request, form.instance, change=False
                )
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(
                    request, obj, change=True
                )

        if not add and not self.has_change_permission(request, obj):
            readonly_fields = flatten_fieldsets(fieldsets)
        else:
            readonly_fields = self.get_readonly_fields(request, obj)
        admin_form = helpers.AdminForm(
            form,
            list(fieldsets),
            # Clear prepopulated fields on a view-only form to avoid a crash.
            self.get_prepopulated_fields(request, obj)
            if add or self.has_change_permission(request, obj)
            else {},
            readonly_fields,
            model_admin=self,
        )
        media = self.media + admin_form.media

        inline_formsets = self.get_inline_formsets(
            request, formsets, inline_instances, obj
        )
        for inline_formset in inline_formsets:
            media += inline_formset.media

        if add:
            title = _("Add %s")
        elif self.has_change_permission(request, obj):
            title = _("Change %s")
        else:
            title = _("View %s")

        context = {
            **self.admin_site.each_context(request),
            "title": title % self.opts.verbose_name,
            "subtitle": str(obj) if obj else None,
            "adminform": admin_form,
            "object_id": object_id,
            "original": obj,
            "is_popup": IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
            "to_field": to_field,
            "media": media,
            "inline_admin_formsets": inline_formsets,
            "errors": helpers.AdminErrorList(form, formsets),
            "preserved_filters": self.get_preserved_filters(request),
        }

        # Hide the "Save" and "Save and continue" buttons if "Save as New" was
        # previously chosen to prevent the interface from getting confusing.
        if (
                request.method == "POST"
                and not form_validated
                and "_saveasnew" in request.POST
        ):
            context["show_save"] = False
            context["show_save_and_continue"] = False
            # Use the change template instead of the add template.
            add = False

        context.update(extra_context or {})

        return self.render_change_form(
            request, context, add=add, change=not add, obj=obj, form_url=form_url
        )

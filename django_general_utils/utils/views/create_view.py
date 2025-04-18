from django.core.exceptions import ValidationError
from django.views.generic import CreateView as GenericCreateView


class CreateView(GenericCreateView):
    def form_valid(self, form):
        try:
            return super(CreateView, self).form_valid(form)
        except ValidationError as e:
            for _field, _error in e.error_dict.items():
                form.add_error(_field, _error)

            return self.form_invalid(form)

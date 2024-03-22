from django.forms import ModelMultipleChoiceField as BaseModelMultipleChoiceField


class ModelMultipleChoiceField(BaseModelMultipleChoiceField):
    _label_from_instance = None

    def __init__(self, *args, **kwargs):
        self._label_from_instance = kwargs.pop('label_from_instance', None)

        super(ModelMultipleChoiceField, self).__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        if self._label_from_instance is not None:
            return self._label_from_instance(obj)

        return super().label_from_instance(obj)

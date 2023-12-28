from rest_framework import serializers


class MultipleChoiceField(serializers.MultipleChoiceField):
    def to_representation(self, value):
        return list(super().to_representation(value))
